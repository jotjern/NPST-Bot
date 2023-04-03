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
        "snabel-a": "https://wiarnvnpsjysgqbwigrn.supabase.co/rest/v1/messages?select="
                    "id%2Crelease_at%2Csender%2Crecipient%2Ccc%2Ctopic%2Ccontent%2Crelease_after_solve%28flag%29"
    }

    def __init__(self, *args, config_file="config.yaml", **kwargs):
        if "intents" not in kwargs:
            kwargs["intents"] = discord.Intents.all()

        with open(config_file, "r", encoding="utf-8") as fr:
            self.config = yaml.load(fr, Loader=yaml.FullLoader)

        self.scoreboard_cache = None
        self.mail_channel: Optional[discord.TextChannel] = None
        self.mod_channel: Optional[discord.TextChannel] = None
        self.mail_acknowledged = []
        super().__init__(*args, **kwargs)

    async def on_ready(self):
        print(f"Bot started as {self.user}")

        if not self.config.get("mail-channel"):
            return
        if not self.config.get("login") or not (self.config["login"].get("email") or self.config["login"].get("password")):
            return

        if os.path.exists("mail-acknowledge.json"):
            with open("mail-acknowledge.json", "r", encoding="utf-8") as fr:
                self.mail_acknowledged = json.load(fr)

            if not self.mail_acknowledged:
                return
        else:
            self.mail_acknowledged = []

        self.mail_channel = await self.fetch_channel(self.config["mail-channel"])\
            if self.config.get("mail-channel") else None
        self.mod_channel = await self.fetch_channel(self.config["moderator-channel"])\
            if self.config.get("moderator-channel") else None

        if not self.mail_channel:
            return

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
                    if mail["id"] in self.mail_acknowledged:
                        continue

                    self.mail_acknowledged.append(mail["id"])

                    attachments = []
                    for match in re.finditer(r"\[(.*)]\((https?://.*)\)", mail["content"]):
                        fname, url = match.groups()
                        attachments.append(url)

                    date = datetime.strptime(
                        mail["release_at"], "%Y-%m-%dT%H:%M:%S+00:00") + timedelta(hours=1)

                    title = (f"Fra: {mail['sender']}\n" +
                             f"Sendt: {datetime.strftime(date, '%d %b %H:%M:%S')}\n" +
                             f"Til: Alle\n" +
                             (f"CC: {mail['cc']}\n" if mail['cc'] else '') +
                             f"Emne: {mail['topic']}")

                    description = mail["content"].replace(
                        "{{brukernavn}}", "hjelpere")

                    mail_msg = await self.mail_channel.send(
                        embed=discord.Embed(
                            title=title,
                            description=description,
                            color=0xff0000
                        )
                    )

                    # Publish the message to other servers if it's in a news channel
                    if mail_msg.channel.type == discord.ChannelType.news:
                        await mail_msg.publish()

                    with open("mail-acknowledge.json", "w", encoding="utf-8") as fw:
                        json.dump(self.mail_acknowledged, fw)

            time_now = datetime.now()
            next_challenge = datetime(
                year=time_now.year, month=time_now.month, day=time_now.day, hour=18)
            seconds_from_new_challenge = (time_now - next_challenge).seconds

            if abs(seconds_from_new_challenge) > 5:
                await asyncio.sleep(min(self.config.get("mail-check-delay", 60), seconds_from_new_challenge - 5))
            else:
                await asyncio.sleep(1)

    async def audit_message(self, msg: discord.Message):
        if not self.config.get("moderate", False):
            return
        if isinstance(msg.channel, discord.DMChannel):
            return
        if msg.author.id == self.user.id:
            return

        if msg.channel.name == "cryptobins":
            if "https://cryptobin.co/" not in msg.content:
                await msg.delete()
                temp_msg = await msg.channel.send("Vennligst kun send cryptobins i denne kanalen!")
                await asyncio.sleep(5)
                await temp_msg.delete()

        # Match for CTF flags
        if re.match(r"N?PST{[^}]{6,}}", msg.content):
            await msg.delete()
            temp_msg = await msg.channel.send("Vennligst ikke send flagg!")
            await asyncio.sleep(5)
            await temp_msg.delete()

            if self.mod_channel:
                await self.mod_channel.send(
                    f"Flagg sendt i {msg.channel.mention} av {msg.author.mention}:"
                    f"```{msg.author}: {discord.utils.escape_mentions(msg.content)}```")

    async def on_message_edit(self, _before, after):
        await self.audit_message(after)

    async def on_message(self, msg: discord.Message):
        await self.audit_message(msg)
        if not msg.content.startswith(self.config.get("prefix", "!")):
            return

        command_name, * \
            command_args = msg.content[len(self.config.get("prefix", "!")):].split(" ")

        command_name = command_name.lower()

        try:
            await self.handle_command(msg, command_name, command_args)
        except Exception as _:
            await msg.reply("`Noe gikk galt 🤖`")
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
        elif command_name == "hjelp" or command_name == "help":
            prefix = self.config.get("prefix", "!")

            await msg.reply(
                "```" +
                "Kommandoer:\n" +
                f"{prefix}topp - sjekk hvor mange som har toppscore og hvor mange som er på scoreboardet\n" +
                f"{prefix}score - se scoreboard\n" +
                f"{prefix}score #[plass] - se scoreboard fra en plassering\n" +
                f"{prefix}score [person] - se score og plassering til en person\n" +
                f"{prefix}flagg - få dagens flagg\n" +
                f"{prefix}regler - få reglene\n" +
                f"{prefix}ping - sjekk om boten er oppe\n" +
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

    @staticmethod
    async def command_ping(msg: discord.Message, _):
        await msg.reply("Pong!")

    async def command_purgemail(self, msg: discord.Message, _):
        if not msg.author.guild_permissions.administrator:
            await msg.add_reaction("❌")
            return

        if self.mail_channel is None:
            await msg.reply("Please wait")
            return

        print("Purging mail channel")

        await self.mail_channel.purge(limit=100)

        self.mail_acknowledged = []
        with open("mail-acknowledge.json", "w", encoding="utf-8") as fw:
            json.dump(self.mail_acknowledged, fw)

    async def command_topp(self, msg: discord.Message, _):
        scoreboard = self.get_scoreboard()

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
            description=(
                "\n".join(set(
                    (
                        f"**{n_best_score} av {len(scoreboard)}** ({pct_best_score}%) på scoreboardet har " +
                        self.format_score(best_score_person) + "\n" +
                        f"**{n_most_flags} av {len(scoreboard)}** ({pct_most_flags}%) på scoreboardet har " +
                        self.format_score(most_flags_person, eggs=False) + "\n" +
                        f"**{n_most_eggs} av {len(scoreboard)}** ({pct_most_eggs}%) på scoreboardet har " +
                        self.format_score(most_eggs_person, flags=False)).split("\n")
                    )
                )
            )
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

        if len(args) >= 1:
            if args[0].startswith("#") or args[0].startswith("*"):
                try:
                    scoreboard = scoreboard[max(int(args[0][1:]) - 1, 0):]
                except ValueError:
                    pass
            else:
                scoreboard = [person for person in scoreboard if person["username"].lower(
                ).startswith(args[0].lower())]

        if len(scoreboard) == 0:
            await msg.reply("Ingen brukere funnet")
        else:
            await msg.reply(embed=discord.Embed(description="\n".join([
                self.format_user(person) for i, person in enumerate(scoreboard[:10])
            ])))

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


def main():
    bot = NPSTBot()
    bot.run()


if __name__ == "__main__":
    main()
