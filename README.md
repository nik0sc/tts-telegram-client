# SUTD Temperature Tracking System Telegram client

This is an unofficial Telegram client for the declaration system at [tts.sutd.edu.sg](tts.sutd.edu.sg).

You'll need Selenium with Firefox, the Telegram API for Python, and `systemd.journal` (I have no idea where I got this from. Is it installed for you if you have systemd? No idea man.)

Before running, you need to put some credentials in a file `ttscreds.json`:

```
{
  "AD_USERNAME": "your AD username",
  "AD_PASSWORD": "your AD password",
  "TG_TOKEN": "telegram bot token",
  "TG_USERID": "your telegram id"
}
```

AD username and password should be pretty self-explanatory. You'll need to change the password when your password expires.

You need your own Telegram bot token. Hit up `@botfather` on Telegram to create your own bot.

You also need to find our your Telegram user id. Hit up `@jsondumpbot` to find that out.

There is a sample systemd unit file for this bot. It assumes that you created a new user `tts` just for this bot, you installed a virtualenv in `~tts` and the files in this repo are also in `~tts`.

## MUST READ

**Do not put the `selenium_` functions in your crontab.** Remember what `/declare_movement` says: if you're caught, you're going to the joint.

For the avoidance of doubt:

**If you actually have a temperature above 37.6℃, have any symptoms of COVID-19 or any other illness, or have been in contact with someone under SHN or who meets the first two conditions, or if you meet any other conditions that may prevent you from truthfully declaring your status as it is declared by this bot, do not use this bot to falsely declare your status.**

**By using this bot you agree to indemnify and hold harmless myself for any consequences of your use of this bot. If you do not consent to these terms, do not use this bot.**

Didn't understand that? Go up and read this section again until you do.

## TODO

The `ensure_user` stuff doesn't work. Maybe someone who knows how Telegram API works can figure that out.

Telegram for Python handles messages sequentially, so an earlier command can block a later one. The `global_lock` doesn't actually do anything.

Anyone can declare your temperature on your behalf. This wasn't a problem when I used this but it might be if enough people know about it. A decent start is to pick a sufficiently random username for your own bot instance.
