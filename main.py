import requests
import discord
import yaml

with open("config.yaml", "r", encoding="utf-8") as fr:
    config = yaml.load(fr, Loader=yaml.FullLoader)

api_endpoints = {
    "scoreboard": "https://wiarnvnpsjysgqbwigrn.supabase.co/rest/v1/scoreboard?select=*"
}

bot = discord.Client()


@bot.event
async def on_ready():
    print(f"Bot started as {bot.user}")


@bot.event
async def on_message(msg: discord.Message):
    if not msg.content.startswith(config["prefix"]):
        return
    command_name, *command_args = msg.content[len(config["prefix"]):].split(" ")
    if command_name == "ping":
        await command_ping(msg, command_args)
    elif command_name == "score":
        await command_score(msg, command_args)


def format_user(username, score, placement):
    return f"#{placement} **{username}**: {score} poeng"


async def command_ping(msg: discord.Message, _):
    await msg.channel.send("Pong!")


async def command_score(msg: discord.Message, args):
    resp = requests.get(api_endpoints["scoreboard"], headers={"apikey": config["api_key"]})

    if resp.status_code == 200:
        scoreboard = resp.json()

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
    else:
        await msg.channel.send("Noe gikk galt!")


if __name__ == "__main__":
    bot.run(config["bot_key"])
