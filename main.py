from datetime import datetime, timedelta

import requests
import asyncio
import discord
import random
import yaml
import json
import time
import math
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

        if not mail_acknowledged:
            return
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

                mail_msg = await mail_channel.send(
                    f"```Fra: {mail['sender']}\n" +
                    f"Sendt: {datetime.strftime(date, '%d %b %H:%M:%S')}\n" +
                    f"Til: Alle\n" +
                    (f"CC: {mail['cc']}\n" if mail['cc'] else '') +
                    f"Emne: {mail['topic']}```" +
                    "```" + mail["content"].replace("{{brukernavn}}", "hjelpere") + "```\n" +
                    "\n".join(attachments)
                )

                # Publish the message to other servers if it's in a news channel
                if mail_msg.channel.type == discord.ChannelType.news:
                    await mail_msg.publish()

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
    if msg.author.id != bot.user.id and msg.channel.name == "cryptobins":
        if "https://cryptobin.co/" not in msg.content:
            await msg.delete()
            temp_msg = await msg.channel.send("Vennligst kun send cryptobins i denne kanalen!")
            await asyncio.sleep(5)
            await temp_msg.delete()

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

    elif command_name == "alle" or command_name == "all":
        await msg.reply(f"Har slått sammen {config['prefix']}topp og {config['prefix']} til !topp, men her:")
        await command_topp(msg, command_args)

    elif command_name == "hjelp" or command_name == "help":
        await msg.reply(
            "```" +
            "Kommandoer:\n" +
            f"{config['prefix']}topp - sjekk hvor mange som har toppscore og hvor mange som er på scoreboardet\n" +
            f"{config['prefix']}score - se scoreboard\n" +
            f"{config['prefix']}score #[plass] - se scoreboard fra en plassering\n" +
            f"{config['prefix']}score [person] - se score og plassering til en person\n" +
            f"{config['prefix']}flagg - få dagens flagg\n" +
            "```"
        )
    elif command_name == "regler" or command_name == "rules":
        await msg.reply("<#652630206804131902>")

    elif command_name == "flagg":
        await msg.reply("PST{finn_det_selv}")

    elif command_name == "egg":
        await msg.reply(random.choice([
            "https://tenor.com/view/you-win-an-egg-ostrich-egg-egg-giant-egg-massive-egg-gif-15032525",
            "https://tenor.com/view/egg-frank-can-i-offer-you-a-nice-egg-in-this-trying-time-gif-13802522"
        ]))


def format_score(score, n_solves):
    flags = (score - n_solves) / 9
    eggs = n_solves - flags
    if math.floor(flags) == flags:  # Sanity check
        return f"🚩 {int(flags)}" + (f" ⭐ {int(eggs)}" if eggs else "")
    else:
        return f"{score} poeng"


def format_user(username, score, n_solves, placement):
    return f"#{placement}{' ' if placement != 10 else ''} {'👑 ' if placement == 1 else ''}" +\
           f"**{discord.utils.escape_markdown(username)}**: {format_score(score, n_solves)}"


def pad(string, length):
    return string + " " * (length - len(string))

async def command_ping(msg: discord.Message, _):
    await msg.reply("Pong!")


async def command_purgemail(msg: discord.Message, _):
    global mail_acknowledged

    if not msg.author.guild_permissions.administrator:
        await msg.add_reaction("❌")
        return

    if mail_channel is None:
        await msg.reply("Please wait")
        return

    print("Purging mail channel")

    await mail_channel.purge(limit=100)

    mail_acknowledged = []
    with open("mail-acknowledge.json", "w", encoding="utf-8") as fw:
        json.dump(mail_acknowledged, fw)


async def command_topp(msg: discord.Message, _):
    scoreboard = get_scoreboard()

    best_score_person = max([person for person in scoreboard], key=lambda person: person["score"])
    n_best_score = len([person for person in scoreboard if person["score"] == best_score_person["score"]])
    await msg.reply(
        f"{n_best_score} av {len(scoreboard)} på scoreboardet har " +
        format_score(best_score_person["score"], best_score_person["num_solves"])
    )


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

    if len(args) == 0 or args[0].startswith("#"):
        start = 0
        if len(args) == 1 and args[0].startswith("#"):
            try:
                start = int(args[0][1:]) - 1
            except ValueError:
                pass
            else:
                start = max(start, 0)
        scoreboard_segment = scoreboard[start:start+10]
        if len(scoreboard_segment) == 0:
            await msg.reply("Ingen brukere funnet")
        else:
            await msg.reply(embed=discord.Embed(description="\n".join([
                format_user(
                    person["username"], person["score"], person["num_solves"], start + i + 1
                ) for i, person in enumerate(scoreboard_segment)
            ])))
    else:
        user_search = args[0]
        for i, person in enumerate(scoreboard):
            if not person["username"].lower().startswith(user_search.lower()):
                continue

            await msg.reply(embed=discord.Embed(
                description=format_user(person["username"], person["score"], person["num_solves"], i + 1)
            ))
            break
        else:
            await msg.reply(f"Fant ikke den brukeren")


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
