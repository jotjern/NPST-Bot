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

from typing import Optional, Tuple


class NPSTBot(discord.Client):
    api_endpoints = {
        "scoreboard": "https://wiarnvnpsjysgqbwigrn.supabase.co/rest/v1/scoreboard?select=*",
        "snabel-a": "https://wiarnvnpsjysgqbwigrn.supabase.co/rest/v1/messages?select=id%2Crelease_at%2Csender%2Crecipient%2Ccc%2Ctopic%2Ccontent%2Crelease_after_solve%28flag%29"
    }

    def __init__(self, *args, config_file="config.yaml", **kwargs):
        if "intents" not in kwargs:
            kwargs["intents"] = discord.Intents.all()

        with open(config_file, "r", encoding="utf-8") as fr:
            self.config = yaml.load(fr, Loader=yaml.FullLoader)

        self.scoreboard_cache = None
        self.mail_channel: Optional[discord.TextChannel] = None
        self.mail_acknowledged = []
        super().__init__(*args, **kwargs)

    async def on_ready(self):
        global mail_channel, mail_acknowledged

        print(f"Bot started as {bot.user}")

        if not self.config["mail-channel"]:
            return
        if not self.config["login"] or not (self.config["login"]["email"] or self.config["login"]["password"]):
            return

        if os.path.exists("mail-acknowledge.json"):
            with open("mail-acknowledge.json", "r", encoding="utf-8") as fr:
                mail_acknowledged = json.load(fr)

            if not mail_acknowledged:
                return
        else:
            mail_acknowledged = []

        mail_channel = await bot.fetch_channel(self.config["mail-channel"])

        while True:
            print("Checking mail")

            session = self.get_login_session()
            resp = requests.get(self.api_endpoints["snabel-a"], headers={
                "apikey": self.config["api_key"],
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

                    date = datetime.strptime(
                        mail["release_at"], "%Y-%m-%dT%H:%M:%S+00:00") + timedelta(hours=1)

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
            next_challenge = datetime(
                year=time_now.year, month=time_now.month, day=time_now.day, hour=18)
            seconds_from_new_challenge = (time_now - next_challenge).seconds

            if abs(seconds_from_new_challenge) > 5:
                await asyncio.sleep(min(self.config["mail-check-delay"], seconds_from_new_challenge - 5))
            else:
                await asyncio.sleep(1)

    async def on_message_edit(self, before, after):
        if after.author.id != bot.user.id and after.channel.name == "cryptobins":
            if "https://cryptobin.co/" not in after.content:
                await after.delete()
                temp_msg = await after.channel.send("Vennligst kun send cryptobins i denne kanalen!")
                await asyncio.sleep(5)
                await temp_msg.delete()

    async def on_message(self, msg: discord.Message):
        if msg.author.id != bot.user.id and msg.channel.name == "cryptobins":
            if "https://cryptobin.co/" not in msg.content:
                await msg.delete()
                temp_msg = await msg.channel.send("Vennligst kun send cryptobins i denne kanalen!")
                await asyncio.sleep(5)
                await temp_msg.delete()

        if not msg.content.startswith(self.config["prefix"]):
            return

        command_name, * \
            command_args = msg.content[len(self.config["prefix"]):].split(" ")

        command_name = command_name.lower()

        try:
            self.handle_command(msg, command_name, command_args)
        except Exception as e:
            msg.reply("`Noe gikk galt 🤖`")
            raise

    async def handle_command(self, msg: discord.Message, command_name: str, command_args: list):
        if command_name == "ping":
            await self.command_ping(msg, command_args)
        elif command_name == "score":
            await self.command_score(msg, command_args)
        elif command_name == "purgemail":
            await self.command_purgemail(msg, command_args)
        elif command_name == "topp":
            await self.command_topp(msg, command_args)
        elif command_name == "alle" or command_name == "all":
            await msg.reply(f"Har slått sammen {self.config['prefix']}topp og {self.config['prefix']} til !topp, men her:")
            await self.command_topp(msg, command_args)
        elif command_name == "hjelp" or command_name == "help":
            await msg.reply(
                "```" +
                "Kommandoer:\n" +
                f"{self.config['prefix']}topp - sjekk hvor mange som har toppscore og hvor mange som er på scoreboardet\n" +
                f"{self.config['prefix']}score - se scoreboard\n" +
                f"{self.config['prefix']}score #[plass] - se scoreboard fra en plassering\n" +
                f"{self.config['prefix']}score [person] - se score og plassering til en person\n" +
                f"{self.config['prefix']}flagg - få dagens flagg\n" +
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

    @staticmethod
    def unpack_score(score, n_solves) -> Tuple[int, int]:
        flags = (score - n_solves) / 9
        eggs = n_solves - flags
        assert math.floor(flags) == flags
        return int(flags), int(eggs)

    @staticmethod
    def format_score(person, flags=True, eggs=True):
        if person["flags"] is None:
            return f"{person['score']} poeng"
        return (
            (f"🚩 {person['flags']} " if person['flags'] and flags else "") +
            (f"⭐ {person['eggs']}" if person['eggs'] and eggs else "")
        )

    @staticmethod
    def format_user(person):
        placement = person["index"] + 1
        return f"#{placement}{' ' if placement != 10 else ''} {'👑 ' if placement == 1 else ''}" +\
            f"**{NPSTBot.clean_username(person['username'])}**: {NPSTBot.format_score(person)}"

    @staticmethod
    def clean_username(username):
        return discord.utils.escape_markdown(username.replace(":crown:", "💩").replace("👑", "💩"))

    async def command_ping(self, msg: discord.Message, _):
        await msg.reply("Pong!")

    async def command_purgemail(self, msg: discord.Message, _):
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

    async def command_topp(self, msg: discord.Message, _):
        scoreboard = self.get_scoreboard()

        print(scoreboard[:10])

        best_score_person = max(
            [person for person in scoreboard], key=lambda person: person["score"] or 0)
        most_flags_person = max(
            [person for person in scoreboard], key=lambda person: person["flags"] or 0)
        most_eggs_person = max([person for person in scoreboard],
                               key=lambda person: person["eggs"] or 0)

        n_best_score = len(
            [person for person in scoreboard if person["score"] == best_score_person["score"]])
        n_most_flags = len(
            [person for person in scoreboard if person["flags"] == most_flags_person["flags"]])
        n_most_eggs = len(
            [person for person in scoreboard if person["eggs"] == most_eggs_person["eggs"]])

        pct_best_score = "{:10.2f}".format(
            100 * n_best_score / len(scoreboard))
        pct_most_flags = "{:10.2f}".format(
            100 * n_most_flags / len(scoreboard))
        pct_most_eggs = "{:10.2f}".format(100 * n_most_eggs / len(scoreboard))

        await msg.reply(embed=discord.Embed(
            description=("\n".join(set((f"**{n_best_score} av {len(scoreboard)}** ({pct_best_score}%) på scoreboardet har " +
                                        self.format_score(best_score_person) + "\n" +
                                        f"**{n_most_flags} av {len(scoreboard)}** ({pct_most_flags}%) på scoreboardet har " +
                                        self.format_score(most_flags_person, eggs=False) + "\n" +
                                        f"**{n_most_eggs} av {len(scoreboard)}** ({pct_most_eggs}%) på scoreboardet har " +
                                        self.format_score(most_eggs_person, flags=False)).split("\n"))))
        ))

    def get_scoreboard(self):
        if self.scoreboard_cache is None or time.time() - self.scoreboard_cache["time"] > 5:
            resp = requests.get(self.api_endpoints["scoreboard"], headers={
                                "apikey": self.config["api_key"]})

            assert resp.status_code == 200

            scoreboard = resp.json()
            for i, person in enumerate(scoreboard):
                person["index"] = i
                try:
                    person["flags"], person["eggs"] = self.unpack_score(
                        person["score"], person["num_solves"])
                except AssertionError:
                    person["flags"], person["eggs"] = None, None
            self.scoreboard_cache = {
                "scoreboard": scoreboard, "time": time.time()}
        else:
            scoreboard = self.scoreboard_cache["scoreboard"]
        return scoreboard

    async def command_score(self, msg: discord.Message, args):
        scoreboard = self.get_scoreboard()

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
                    self.format_user(person) for i, person in enumerate(scoreboard_segment)
                ])))
        else:
            user_search = args[0]
            for i, person in enumerate(scoreboard):
                if not person["username"].lower().startswith(user_search.lower()):
                    continue

                await msg.reply(embed=discord.Embed(
                    description=self.format_user(person)
                ))
                break
            else:
                await msg.reply(f"Fant ikke den brukeren")

    def get_login_session(self):
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
                "apikey": self.config["api_key"]
            }, json={
                "email": self.config["login"]["email"],
                "password": self.config["login"]["password"]
            })

            session = resp.json()
            assert "error" not in session, session["error"]

            with open("session.json", "w", encoding="utf-8") as fw:
                json.dump(
                    {"session": session, "session_created": time.time()}, fw, indent=4)

        return session

    def run(self, *args, **kwargs):
        super().run(self.config["bot_key"], *args, **kwargs)


if __name__ == "__main__":
    bot = NPSTBot()
    bot.run()
