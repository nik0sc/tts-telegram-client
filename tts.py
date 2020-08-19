from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoAlertPresentException
from selenium.webdriver.firefox.options import Options
from datetime import datetime
from socket import gethostname
import telegram
from telegram.ext import Updater, CommandHandler
from systemd.journal import JournaldLogHandler
import random
import time
import traceback
import argparse
import logging
import json
import threading


TTS_HOST = 'https://tts.sutd.edu.sg'
TTS_LOGIN = '/tt_login.aspx?formmode=expire'
TTS_LOGIN_BASENAME = 'tt_login.aspx'
TTS_LOGIN_USER_INPUT = 'pgContent1_uiLoginid'
TTS_LOGIN_PASS_INPUT = 'pgContent1_uiPassword'
TTS_LOGIN_SUBMIT = 'pgContent1_btnLogin'

TTS_TEMP = '/tt_temperature_taking_user.aspx'
TTS_TEMP_INPUT = 'pgContent1_uiTemperature'
TTS_TEMP_SUBMIT = 'pgContent1_btnSave'
TTS_TEMP_HEALTHY = 'Less than or equal to 37.6°C'
# Ordered most recent first
TTS_TEMP_LIST_RECENT_XPATH = '//div[@id=\'list\']//tr[@class=\'listrow\'][1]/td'
TTS_TEMP_LIST_FIELDS = ('', '', 'Timestamp', 'Declaration', 'Comments')

TTS_MOVEMENT = '/tt_daily_dec_user.aspx'
TTS_MOVEMENT_RADIOS = ('pgContent1_rbVisitOtherCountryNo', 
    'pgContent1_rbNoticeNo',
    'pgContent1_rbContactNo',
    'pgContent1_rbMCNo')
TTS_MOVEMENT_CHECKBOXES_XPATH = '//div[@id=\'form\']//input[@type=\'checkbox\']'
TTS_MOVEMENT_SUBMIT = 'pgContent1_btnSave'
# Ordered most recent last
TTS_MOVEMENT_LIST_RECENT_XPATH = '//div[@id=\'list\']//tr[@class=\'listrow\'][last()]/td'
TTS_MOVEMENT_LIST_FIELDS = ('', '', 'Timestamp', 'Travelled?', 'Countries', 'Quarantine?', 'Close contact?', 'MC?', 'Fever?', 'Dry cough?', 'Shortness of breath?', 'Sore throat?', 'Runny nose?', '')

AD_USERNAME = '' # in ttscreds.json
AD_PASSWORD = '' # in ttscreds.json

TG_TOKEN = '' # in ttscreds.json
TG_MESSAGE_TEMP_SUCCESS = '✅ Temperature declaration completed at {0}:\n\n{1}\n\n🤒 Please remember to take your temperature though'
TG_MESSAGE_MOVEMENT_SUCCESS = '✅ Movement declaration completed at {0}:\n\n{1}\n\n👮 If you lie on this, you\'re going to the joint'
TG_MESSAGE_FAIL = '💣 *Unhandled exception in {0}():*\n\n```\n{1}\n```\n\n'
TG_MESSAGE_CREDS = '🔐❌ *Can\'t log in!*\n\nMaybe you need to update your username and password.'
TG_MESSAGE_BUSY = '⏳ Bot is still processing your last request... (This one won\'t be processed.)'
TG_MESSAGE_SLEEP = 'Bot is awake, sleeping for {0} seconds...'
TG_MESSAGE_NOT_AUTHORISED = '⛔ You\'re not authorised to use this bot.'
TG_MESSAGE_NOT_AUTHORISED_2 = '👀 Another user tried to use this bot:\n\nUser ID: {0}\nName:{1} {2}\nHandle:{3}'
TG_USERID = '' # in ttscreds.json

MAX_DELAY = 1800

logger = logging.getLogger(__name__)
journald_handler = JournaldLogHandler()
journald_handler.setFormatter(logging.Formatter(
    '[%(levelname)s] %(message)s'
))
logger.addHandler(journald_handler)
logger.setLevel(logging.INFO)

global_lock = threading.RLock()


def ensure_login(dr, url):
    dr.get(TTS_HOST + url)

    if TTS_LOGIN_BASENAME in dr.current_url:
        # do login
        user_input = dr.find_element_by_id(TTS_LOGIN_USER_INPUT)
        user_input.send_keys(AD_USERNAME)
        pass_input = dr.find_element_by_id(TTS_LOGIN_PASS_INPUT)
        pass_input.send_keys(AD_PASSWORD)
        submit = dr.find_element_by_id(TTS_LOGIN_SUBMIT)
        submit.click()
        logging.info('login successful')

        dr.get(TTS_HOST + url)
        if url not in dr.current_url:
            raise RuntimeError('can\'t log in')
    else:
        logging.info('login not needed')


def make_report(dr, xpath, fields):
    first_row = dr.find_elements_by_xpath(xpath)     
    out = []
    for field, elem in zip(fields, first_row):
        if not field:
            continue
        out.append(f'{field}: {elem.text.strip()}')
    return out


def selenium_temp():
    opts = Options()
    opts.add_argument('--headless')
    dr = webdriver.Firefox(options=opts)
    out = None

    try:
        ensure_login(dr, TTS_TEMP)
            
        temperature = Select(dr.find_element_by_id(TTS_TEMP_INPUT))
        temperature.select_by_value(TTS_TEMP_HEALTHY)
        submit = dr.find_element_by_id(TTS_TEMP_SUBMIT)
        submit.click()
        logging.info('Submitted temp')

        try:
            dr.switch_to.alert.accept()
        except NoAlertPresentException:
            pass

        out = make_report(dr, TTS_TEMP_LIST_RECENT_XPATH, TTS_TEMP_LIST_FIELDS)
    finally:
        dr.quit()
    
    return '\n'.join(out)


def selenium_movement():
    opts = Options()
    opts.add_argument('--headless')
    dr = webdriver.Firefox(options=opts)
    out = None

    try:
        ensure_login(dr, TTS_MOVEMENT)

        for radio_id in TTS_MOVEMENT_RADIOS:
            dr.find_element_by_id(radio_id).click()

        # Make sure symptom checkboxes are cleared
        checkboxes = dr.find_elements_by_xpath(TTS_MOVEMENT_CHECKBOXES_XPATH)
        for elem in checkboxes:
            if elem.is_selected():
                elem.click()
            assert not elem.is_selected()
        
        dr.find_element_by_id(TTS_MOVEMENT_SUBMIT).click()
        logging.info('Submitted movement')

        try:
            dr.switch_to.alert.accept()
        except NoAlertPresentException:
            pass

        out = make_report(dr, TTS_MOVEMENT_LIST_RECENT_XPATH,
            TTS_MOVEMENT_LIST_FIELDS)
    except:
        logging.error('While in selenium_movement():')
        logging.error(traceback.format_exc())
        raise
    finally:
        dr.quit()

    return '\n'.join(out)


def ensure_user(update, context, valid_id):
    logging.debug('User connecting: chat_id={0} from_user.id={1}'.format(
        update.message.chat_id, update.message.from_user.id
    ))
    if update.message.chat_id != valid_id:
        context.bot.send_message(chat_id=update.message.chat_id,
            text=TG_MESSAGE_NOT_AUTHORISED)
        context.bot.send_message(chat_id=valid_id,
            text=TG_MESSAGE_NOT_AUTHORISED_2.format(
                update.message.chat_id,
                update.message.from_user.first_name,
                update.message.from_user.last_name or '',
                update.message.from_user.user_name or ''))
        return False
    return True


def log_temp(update, context):
    #if not ensure_user(update, context, TG_USERID):
    #    return
    
    if global_lock.acquire(False):
        try:
            # This really should be async
            result = selenium_temp()
            now = datetime.now().isoformat()
            message = TG_MESSAGE_TEMP_SUCCESS.format(now, result)
        except Exception:
            message = TG_MESSAGE_FAIL.format('log_temp',
                traceback.format_exc())
        finally:
            global_lock.release()
            context.bot.send_message(chat_id=TG_USERID, text=message, 
                parse_mode=telegram.ParseMode.MARKDOWN)
    else:
        context.bot.send_message(chat_id=TG_USERID, text=TG_MESSAGE_BUSY)


def log_movement(update, context):
    #if not ensure_user(update, context, TG_USERID):
    #    return

    if global_lock.acquire(False):
        try:
            # This really should be async
            result = selenium_movement()
            now = datetime.now().isoformat()
            message = TG_MESSAGE_MOVEMENT_SUCCESS.format(now, result)
        except Exception:
            message = TG_MESSAGE_FAIL.format('log_movement',
                traceback.format_exc())
        finally:
            global_lock.release()
            context.bot.send_message(chat_id=TG_USERID, text=message, 
                parse_mode=telegram.ParseMode.MARKDOWN)
    else:
        context.bot.send_message(chat_id=TG_USERID, text=TG_MESSAGE_BUSY)


def setup():
    try:
        with open('ttscreds.json') as f:
            data = json.load(f)
    except:
        logging.error('Cannot open ttscreds.json')
        raise
        
    for k,v in data.items():
        globals()[k] = v

    logging.info('Bot start')
    updater = Updater(token=TG_TOKEN, use_context=True)
    updater.bot.send_message(chat_id=TG_USERID,
            text=f'🤖 Bot start on {gethostname()}')
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('declare_temp', log_temp))
    dispatcher.add_handler(CommandHandler('declare_movement', log_movement))
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    setup()



