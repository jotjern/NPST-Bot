import discord

bot = discord.Client()


@bot.event
async def on_message(msg: discord.Message):
    if msg.content == "!ping":
        await msg.channel.send("Pong!")

if __name__ == "__main__":
    with open("token.txt", "r", encoding="utf-8") as fr:
        token = fr.read().strip()

    bot.run(token)
