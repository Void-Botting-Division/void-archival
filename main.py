# PD: (if you see this code kinda awful is because) I hate writing Python code :). And before you ask no i dont use AI
import subprocess
from asyncio import sleep
import discord
import os
import shutil
import signal
from typing import Any
from json import load, dump
from enum import Enum
from configparser import ConfigParser
from multiprocessing import Pool, current_process

config = ConfigParser()
config.read("settings.ini")

# aliases to config
botToken = config["settings"]["botToken"]
serverToOutput = config["settings"].getint("output")
serverToArchive = config["settings"].getint("archive")

catConf = "do-not-touch.oldCategories"
hookConf = "do-not-touch.hookChannels"
Conf = "do-not-touch"

# paths
outputPath = os.path.join(os.getcwd(), "output/")
cExporterPath = os.path.join(os.getcwd(), "DiscordChatExporter/DiscordChatExporter.Cli")


# ? Is this how * works? lmao help
async def main(rmDir: bool, *, checkChannels: bool, client: discord.Client):
    oldCategories = {}  # old category id that pinpoints to new category id
    hookChannels = {}  # new channel id that pinpoints to webhook

    # * Before everything
    if rmDir:
        if os.path.isdir(outputPath):
            shutil.rmtree(outputPath)
    if checkChannels:
        print(">> Fetching channels to archive...")
        # Cleans old fetched data
        config[catConf] = {}
        config[hookConf] = {}
        await getChannelOutput()

    #! Fixing errors :)
    if (
        not config.has_section(catConf)
        and not config.has_section(hookConf)
        and not config.has_section(Conf)
    ):
        config.add_section(catConf)
        config.add_section(hookConf)
        config.add_section(Conf)

    # * Get old cats and hooks from settings
    for cat in config[catConf]:
        oldCategories[cat] = config[catConf].getint(cat)
    for h in config[hookConf]:
        hookChannels[h] = config[hookConf][h]

    def saveToConf(section: str, key: str, val: str):
        match section:
            # i fucking hate Python
            case "do-not-touch.oldCategories":
                oldCategories[key] = val
            case "do-not-touch.hookChannels":
                hookChannels[key] = val
        config[section][key] = val

    # * func declares
    async def createHook(channel: discord.TextChannel) -> discord.Webhook:
        hook = await channel.create_webhook(name="archive")
        # Save it for future archives and config as well
        saveToConf(hookConf, str(channel.id), hook.url)
        return hook

    async def createCategory(catName: str):
        # Create it
        category = await guild.create_category(name=f"Archive - {catName}")
        # Save it for future archives and config as well
        saveToConf(catConf, str(oldCatId), str(category.id))

    # Always a text channel
    #! redeclaring guild again because errors ¯\_(ツ)_/¯
    async def createChannel(guild: discord.Guild, name: str, oldCatId: str):
        category = next(
            filter(
                lambda category: (
                    category if category.id == int(oldCategories[oldCatId]) else None
                ),
                guild.categories,
            )
        )
        return await guild.create_text_channel(name=name, category=category)

    def searchChannel(channelName: str):
        for category in oldCategories.values():
            for channel in guild.text_channels:
                # Check that it is on a archive category
                if channel.category_id == int(category) and channel.name == channelName:
                    return channel

    async def startUpload(hook: discord.Webhook, data: Any):
        for message in data["messages"]:
            try:
                await hook.send(
                    content=message["content"],
                    avatar_url=message["author"]["avatarUrl"],
                    username=message["author"]["name"],
                )
            except discord.errors.HTTPException:
                print("Uh oh! Undefined message found!")

    # ** main continues here
    # Assumes you already have the output
    print(">> Getting server...")

    guild = client.get_guild(serverToOutput)
    if guild is not None:
        await client.change_presence(
            activity=discord.Game("Archive - Creating archive...")
        )
        if len(config[hookConf]) == 0 and len(config[catConf]) == 0:
            # Nothing on config about hooks or channels
            for file in scanOutputDir():
                with open(file, "tr", encoding="utf-8") as tfile:
                    data = load(tfile)
                    oldCatId = data["channel"]["categoryId"]
                    channelName = data["channel"]["name"]

                    # Check that the old categoryid exists on categories
                    if oldCatId not in oldCategories:
                        print(f">> Creating category: {data["channel"]["category"]}")
                        await createCategory(data["channel"]["category"])

                    # search if a channel does not exist
                    c = searchChannel(channelName)
                    if c is None:
                        print(f">> Creating channel: {channelName}")
                        c = await createChannel(guild, channelName, oldCatId)
                        hook = await createHook(c)
                        await startUpload(hook, data=data)
                        print(f">> Done on channel: {channelName}")
                    else:
                        print(
                            ">> Uhhh there seems to be an identical channel in a identical archive category try deleting the whole channel and category (and by extension refetch)"
                        )
                        exit(-1)
            print(">> Done archiving.")
            exit(0)
        else:
            # TODO: Implement time-based update system
            if not config[Conf]["lastUpdate"]:
                print(
                    ">> Seems something went wrong last time. Try refetching the channels!"
                )
                # * Clean
                config[catConf] = {}
                config[hookConf] = {}
                config[Conf] = {}
                exit(-1)
            else:
                pass


def scanOutputDir() -> list[str]:
    path = os.path.join(outputPath, "json/")
    files = []
    for ffile in os.scandir(path):
        if ffile.is_file():
            files.append(ffile.path)
    return files


# Repeat with HtmlDark just in case
arg = [
    [
        cExporterPath,
        "exportguild",
        "-t",
        botToken,
        "-f",
        "Json",
        "-o",
        os.path.join(outputPath, "json/"),
        "-g",
        str(serverToArchive),
    ],
    [
        cExporterPath,
        "exportguild",
        "-t",
        botToken,
        "-f",
        "HtmlDark",
        "-o",
        os.path.join(outputPath, "html/"),
        "-g",
        str(serverToArchive),
    ],
]


def proc_task(pool_id: int):
    # DiscordChatExporter creates folders auto
    result = subprocess.run(
        arg[pool_id],
        shell=True,
        capture_output=True,
    )
    return result


async def getChannelOutput() -> bool:
    print(">> [note] PD: if you see an error here please ignore it, its discord")

    t = 0

    with Pool(processes=2) as pool:
        #! Im getting insane as to not block main thread
        p1 = pool.apply_async(proc_task, args=(0,))
        p2 = pool.apply_async(proc_task, args=(1,))

        while not p1.ready() or not p2.ready():
            await sleep(2)
            t += 2
            text = f'{"Waiting for JSON archive" if not p1.ready() else ""} {"and" if not p2.ready() and not p1.ready() else ""} {"Waiting for HTML archive" if not p2.ready() else ""}'
            print(f">> ({t}s) {text}")
            #* every 12 seconds update discord status as to not block discord thread
            if (t % 12 == 0):
                await client.change_presence(status=discord.Status.do_not_disturb, activity=discord.Game(f"Archive - {text} ({t}s)"))

        result = p1.get()
        result2 = p2.get()

        if (
            # JSON
            isinstance(result, subprocess.CompletedProcess)
            and str(result.stdout).rfind("Successfully") != -1
        ) and (
            # HTML
            isinstance(result2, subprocess.CompletedProcess)
            and str(result2.stdout).rfind("Successfully") != -1
        ):
            print(">> Both copies were done.")
            return True
        else:
            raise ValueError("DiscordChatExporter could not find any channels...")


if __name__ == "__main__":
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_error(event: str):
        config.write(open("settings.ini", "wt"))
        exit(-1)  # Simply put it's only going to run once, not 24/7

    @client.event
    async def on_ready():
        print(">> Checks out")
        guildToArchive = client.get_guild(serverToArchive)
        # i get that DiscordChatExporter does the check anyways, just doing it in case
        if guildToArchive is not None:
            await client.change_presence(
                status=discord.Status.idle,
                activity=discord.Game("Archive - Doing things..."),
            )
            # Check if there are files on "output/"
            if os.path.isdir(outputPath):

                async def question():
                    t = input(
                        ">> Folder found... Do you want to refetch everything? (Y/N): "
                    )
                    match t:
                        case "Y" | "y":
                            print(">> Refetching...")
                            await main(True, checkChannels=True, client=client)
                        case "N" | "n":
                            print(">> Skipping...")
                            await main(False, checkChannels=False, client=client)
                        case _:
                            await question()

                await question()
            else:
                print(">> Folder not found... Fetching channels")
                await main(False, checkChannels=True, client=client)
        else:
            raise ValueError("Guild was not found")

    #! Avoid settings.ini erasing by itself
    
    signal.signal(
        signal.SIGINT,
        lambda _, __: print(">> Aborting and exiting gracefully.")
        and config.write(open("settings.ini", "wt"))
        and exit(0),
    )

    client.run(botToken)
