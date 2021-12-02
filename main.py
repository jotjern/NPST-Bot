from datetime import datetime, timedelta

import requests
import asyncio
import discord
import yaml
import json
import time
import os
import re

from typing import Optional

with open("config.yaml", "r", encoding="utf-8") as fr:
    config = yaml.load(fr, Loader=yaml.FullLoader)
del fr

api_endpoints = {
    "scoreboard": "https://wiarnvnpsjysgqbwigrn.supabase.co/rest/v1/scoreboard?select=*",
    "snabel-a": "https://wiarnvnpsjysgqbwigrn.supabase.co/rest/v1/messages?select=id%2Crelease_at%2Csender%2Crecipient%2Ccc%2Ctopic%2Ccontent%2Crelease_after_solve%28flag%29"
}

mail_acknowledged = []
mail_channel: Optional[discord.TextChannel] = None

scoreboard_cache = None

bot = discord.Client()


@bot.event
async def on_ready():
    global mail_channel, mail_acknowledged

    print(f"Bot started as {bot.user}")

    if not config["mail-channel"]:
        return
    if not config["login"] or not (config["login"]["email"] or config["login"]["password"]):
        return

    if os.path.exists("mail-acknowledge.json"):
        with open("mail-acknowledge.json", "r", encoding="utf-8") as fr:
            mail_acknowledged = json.load(fr)
    else:
        mail_acknowledged = []

    mail_channel = await bot.fetch_channel(config["mail-channel"])

    while True:
        print("Checking mail")

        session = get_login_session()
        resp = requests.get(api_endpoints["snabel-a"], headers={
            "apikey": config["api_key"],
            "authorization": f"Bearer {session['access_token']}"
        })
        if resp.status_code != 200:
            print(f"Failed to check mail, error code:", resp.status_code)
        else:
            for mail in resp.json():
                if mail["id"] in mail_acknowledged:
                    continue

                mail_acknowledged.append(mail["id"])

                attachments = []
                for match in re.finditer(r"\[(.*)\]\((http[s]?:\/\/.*)\)", mail["content"]):
                    fname, url = match.groups()
                    attachments.append(url)

                date = datetime.strptime(mail["release_at"], "%Y-%m-%dT%H:%M:%S+00:00") + timedelta(hours=1)

                await mail_channel.send(
                    f"```Fra: {mail['sender']}\n" +
                    f"Sendt: {datetime.strftime(date, '%d %b %H:%M:%S')}\n" +
                    f"Til: Alle\n" +
                    (f"CC: {mail['cc']}\n" if mail['cc'] else '') +
                    f"Emne: {mail['topic']}```" +
                    "```" + mail["content"].replace("{{brukernavn}}", "hjelpere") + "```\n" +
                    "\n".join(attachments)
                )

                with open("mail-acknowledge.json", "w", encoding="utf-8") as fw:
                    json.dump(mail_acknowledged, fw)

        time_now = datetime.now()
        next_challenge = datetime(year=time_now.year, month=time_now.month, day=time_now.day, hour=18)
        seconds_from_new_challenge = (time_now - next_challenge).seconds

        if abs(seconds_from_new_challenge) > 5:
            await asyncio.sleep(min(config["mail-check-delay"], seconds_from_new_challenge - 5))
        else:
            await asyncio.sleep(1)
            print("FAST SLEEPING")


@bot.event
async def on_message(msg: discord.Message):
    if not msg.content.startswith(config["prefix"]):
        return

    command_name, *command_args = msg.content[len(config["prefix"]):].split(" ")

    if command_name == "ping":
        await command_ping(msg, command_args)

    elif command_name == "score":
        await command_score(msg, command_args)

    elif command_name == "purgemail":
        await command_purgemail(msg, command_args)

    elif command_name == "topp":
        await command_topp(msg, command_args)

    elif command_name == "hjelp" or command_name == "help":
        await msg.channel.send(
            "```" +
            "Kommandoer:\n" +
            "+topp\n" +
            "+score\n" +
            "+score [person]\n" +
            "```"
        )


def format_user(username, score, placement):
    return f"#{placement} {'👑 ' if placement == 1 else ''}**{discord.utils.escape_markdown(username)}**: {score} poeng"


async def command_ping(msg: discord.Message, _):
    await msg.channel.send("Pong!")


async def command_purgemail(msg: discord.Message, _):
    global mail_acknowledged

    if not msg.author.guild_permissions.administrator:
        await msg.add_reaction("❌")
        return

    if mail_channel is None:
        await msg.channel.send("Please wait")
        return

    print("Purging mail channel")

    await mail_channel.purge(limit=100)

    mail_acknowledged = []
    with open("mail-acknowledge.json", "w", encoding="utf-8") as fw:
        json.dump(mail_acknowledged, fw)


async def command_topp(msg: discord.Message, _):
    scoreboard = get_scoreboard()

    best_score = max([person["score"] for person in scoreboard])
    n_best_score = len([person for person in scoreboard if person["score"] == best_score])
    await msg.channel.send(f"Det er {n_best_score} på scoreboardet som har {best_score} poeng")


def get_scoreboard():
    global scoreboard_cache

    if scoreboard_cache is None or time.time() - scoreboard_cache["time"] > 5:
        resp = requests.get(api_endpoints["scoreboard"], headers={"apikey": config["api_key"]})

        assert resp.status_code == 200

        scoreboard = resp.json()
        scoreboard_cache = {"scoreboard": scoreboard, "time": time.time()}
    else:
        scoreboard = scoreboard_cache["scoreboard"]
    return scoreboard


async def command_score(msg: discord.Message, args):
    scoreboard = get_scoreboard()

    if len(args) == 0:
        await msg.channel.send(embed=discord.Embed(description="\n\n".join([
            format_user(person["username"], person["score"], i + 1) for i, person in enumerate(scoreboard[:10])
        ])))

    else:
        user_search = args[0]
        for i, person in enumerate(scoreboard):
            if not person["username"].lower().startswith(user_search.lower()):
                continue

            await msg.channel.send(embed=discord.Embed(
                description=format_user(person["username"], person["score"], i + 1)
            ))
            break
        else:
            await msg.channel.send(f"Fant ikke den brukeren")


def get_login_session():
    session = None
    if os.path.exists("session.json"):
        with open("session.json", "r", encoding="utf-8") as fr:
            session_data = json.load(fr)

        if time.time() - session_data["session_created"] < session_data["session"]["expires_in"]:
            session = session_data["session"]
            print("Using existing login session")
        else:
            print("Login session expired!")

    if session is None:
        print("Creating new login session!")
        resp = requests.post("https://wiarnvnpsjysgqbwigrn.supabase.co/auth/v1/token?grant_type=password", headers={
            "apikey": config["api_key"]
        }, json={
            "email": config["login"]["email"],
            "password": config["login"]["password"]
        })

        session = resp.json()
        assert "error" not in session, session["error"]

        with open("session.json", "w", encoding="utf-8") as fw:
            json.dump({"session": session, "session_created": time.time()}, fw)

    return session


if __name__ == "__main__":
    bot.run(config["bot_key"])
