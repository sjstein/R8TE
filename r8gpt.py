import asyncio
from collections import defaultdict
import discord  # noqa This libray is covered in py-cord
from discord.ext import tasks  # noqa This libray is covered in py-cord
from discord import option  # noqa This libray is covered in py-cord
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import glob
import os
from r8gptInclude import (WORLDSAVE_PATH, AEI_PATH, DB_FILENAME, LOG_FILENAME, AI_ALERT_TIME, PLAYER_ALERT_TIME,
                          REMINDER_TIME, BOT_TOKEN, CH_LOG, CH_ALERT, CH_DETECTOR, CREWED_TAG, COMPLETED_TAG,
                          AVAILABLE_TAG, LOCATION_DB, SCAN_TIME, IGNORED_TAGS, REBOOT_TIME, RED_SQUARE, RED_EXCLAMATION,
                          GREEN_CIRCLE, AXE)
from r8gptInclude import Car, Cut, Train, Player, AeiReport, CarReport
import r8gptDB

DEBUG = True

# Necessary Bot intents
intents = discord.Intents.default()
intents.guilds = True  # noqa
intents.messages = True  # noqa
intents.message_content = True  # noqa

VERSION = '04Aug25'
SAVENAME = WORLDSAVE_PATH + '/Auto Save World.xml'
DIESEL_ENGINE = 'US_DieselEngine'
DISCORD_CHAR_LIMIT = 2000
DISTANCE_JITTER = 1.0       # Difference value used to determine if a train is moving
TMP_FILENAME = 'r8gpt_msg.txt'

event_db = list()


def parse_train_loader(root):
    cuts = list()
    for t in root.iter('TrainLoader'):
        train_id = t.find('trainID').text
        was_ai = t.find('TrainWasAI').text
        direction = t.find('DispatchTrainDirection').text
        speed_limit = t.find('ManuallyAppliedSpeedLimitMPH').text
        prev_signal = t.find('PreviousSignalInstruction').text
        units = list()
        unit_loader = t.find('unitLoaderList')
        for rail_vehicle in unit_loader.iter('RailVehicleStateClass'):
            file_name = rail_vehicle.find('rvXMLfilename').text
            unit_type = rail_vehicle.find('unitType').text
            route_prefix_1 = rail_vehicle.find('currentRoutePrefix')[0].text
            track_index_1 = rail_vehicle.find('currentTrackSectionIndex')[0].text
            start_node_1 = rail_vehicle.find('startNodeIndex')[0].text
            distance_1 = rail_vehicle.find('distanceTravelledInMeters')[0].text
            reverse_1 = rail_vehicle.find('reverseDirection')[0].text
            if len(rail_vehicle.find("currentRoutePrefix")) > 1:
                route_prefix_2 = rail_vehicle.find('currentRoutePrefix')[1].text
                track_index_2 = rail_vehicle.find('currentTrackSectionIndex')[1].text
                start_node_2 = rail_vehicle.find('startNodeIndex')[1].text
                distance_2 = rail_vehicle.find('distanceTravelledInMeters')[1].text
                reverse_2 = rail_vehicle.find('reverseDirection')[1].text
            else:
                route_prefix_2 = None
                track_index_2 = None
                start_node_2 = None
                distance_2 = None
                reverse_2 = None
            load_weight = rail_vehicle.find('loadWeightUSTons').text
            dest_tag = rail_vehicle.find('destinationTag').text
            unit_number = rail_vehicle.find('unitNumber').text
            hazmat_tag = rail_vehicle.find('hazmatPlacardIndex').text
            units.append(
                Car(file_name, unit_type, route_prefix_1, route_prefix_2, track_index_1, track_index_2, start_node_1,
                    start_node_2, distance_1, distance_2, reverse_1, reverse_2, load_weight, dest_tag, unit_number,
                    hazmat_tag))
        cuts.append(Cut(train_id, was_ai, direction, speed_limit, prev_signal, units.copy()))
        units.clear()
    return cuts


def location(route_id, track_index):
    sub = int(route_id)
    trk = int(track_index)

    if sub in LOCATION_DB:
        try:
            return LOCATION_DB[sub]
        except KeyError:
            return route_id
    else:
        return route_id


curr_trains = dict()  # Dict of all trains in the world
watched_trains = dict()  # Dict of trains which are stalled/stuck
players = dict()  # Dict of player controlled trains
alert_messages = defaultdict(list)  # Dict of messages sent to alert channel
detector_reports = defaultdict(list)
detector_files = list()
detector_file_time: float = 0.0

global last_world_datetime

def update_world_state(world_trains):
    symbol_list = list()
    world_trains.clear()
    tree = ET.parse(SAVENAME)
    root = tree.getroot()
    world_save_datetime = datetime.strptime(root.find('date').text.split('.')[0], '%Y-%m-%dT%H:%M:%S')
    cuts = parse_train_loader(root)
    for cut in cuts:
        if cut.consist[0].unit_type == DIESEL_ENGINE:  # We are only interested in consists with lead locos
            tid = cut.train_id
            tag = cut.consist[0].dest_tag
            nbr = cut.consist[0].unit_number
            rp_1 = cut.consist[0].route_1
            rp_2 = cut.consist[0].route_2
            ts_1 = cut.consist[0].track_1
            ts_2 = cut.consist[0].track_2
            dist_1 = cut.consist[0].dist_1
            dist_2 = cut.consist[0].dist_2
            if tag in symbol_list:
                if tag != 'None':
                    pass
                    #print(f'Duplicate symbol: [{tag}] found while parsing world save')
            else:
                symbol_list.append(tag)
            if 'amtrak' in cut.consist[0].filename.lower():
                train_type = 'Passenger'
            else:
                train_type = 'Freight'
            if cut.is_ai is True:
                eng = 'AI'
            else:
                eng = 'None'
            world_trains[tid] = Train(tid, tag, nbr, train_type, len(cut.consist), eng, cut.consist.copy(),
                                      world_save_datetime, rp_1, rp_2, ts_1, ts_2, dist_1, dist_2)
        else:
            # First car is not a locomotive, so not a valid train
            pass
    return world_save_datetime


def find_tid(train_tag, train_list):
    for tid in train_list:
        if train_list[tid].symbol.lower() == train_tag.lower():
            return tid
    return -1


def train_count(train_type, world_trains, watched_trains):
    count = 0
    if train_type.lower() == 'ai':
        for tid in world_trains:
            if world_trains[tid].engineer.lower() == 'ai':
                count += 1
    elif train_type.lower() == 'player':
        for tid in world_trains:
            if world_trains[tid].engineer.lower() != 'none' and world_trains[tid].engineer.lower() != 'ai':
                count += 1
    elif train_type.lower() == 'stuck':
        count = len(watched_trains)
    elif train_type.lower() == 'all':
        count = len(world_trains)
    else:
        count = -1

    return count


def player_crew_train(train_set, tid, discord_id, discord_name, thread, add_time):
    if discord_id in players:
        return -1
    players[discord_id] = Player(discord_id, discord_name, thread, curr_trains[tid].symbol, tid, add_time)
    if tid not in players:
        train_set[tid].engineer = discord_name
        train_set[tid].discord_id = discord_id
        train_set[tid].job_thread = thread
        train_set[tid].last_time_moved = add_time
        print(f'player_crew_train called:\n\nPlayer info:\n{players[discord_id]}\n\nTrain info:\n{train_set[tid]}')
        return 0


def parseAEI(timestamp, root):
    this_report = None
    for t in root.iter('AEI_Report'):
        scanner_name = t.find('scannername').text
        train_symbol = t.find('trainsymbol').text
        train_speed = t.find('trainspeedmph').text
        total_axles = t.find('totalaxles').text
        total_loads = t.find('totalloads').text
        total_empties = t.find('totalmtys').text
        total_tons = t.find('totaltons').text
        total_length = t.find('trainlengthft').text
        units = list()
        unitLoader = t.find('reportdata')
        for rail_vehicle in unitLoader.iter('AEI_Report_UnitData'):
            unit_type = rail_vehicle.find('equipmentype').text
            direction = rail_vehicle.find('direction').text
            sequence =rail_vehicle.find('sequence').text
            roadname = rail_vehicle.find('roadname').text
            unitnumber = rail_vehicle.find('unitnumber').text
            isloaded = rail_vehicle.find('isloaded').text
            cargotons = rail_vehicle.find('cargotons').text
            hazmat = rail_vehicle.find('hazmatPlacardIndex').text
            dest_tag = rail_vehicle.find('destinationtag').text
            defect = rail_vehicle.find('cardefect').text
            file_name = rail_vehicle.find('carfilename').text
            units.append(
                CarReport(unit_type, direction, sequence, roadname, unitnumber, isloaded, cargotons, hazmat, dest_tag,
                          defect, file_name))
        this_report = AeiReport(scanner_name, timestamp, train_symbol, train_speed, total_axles, total_loads,
                                total_empties,total_tons, total_length, units)

    return this_report


def log_msg(msg):
    with open(LOG_FILENAME, 'a') as fp:
        fp.write(msg + '\n')


bot = discord.Bot(intents=intents)


async def send_ch_msg(ch_name, ch_msg):
    """
    Send messages to discord channel
    :param ch_name: name of discord channel to write message to
    :param ch_msg: Message content
    :return: 0 if successful, -1 if error
    """
    if ch_msg.lower() == 'none':
        return 0

    if len(ch_msg) > DISCORD_CHAR_LIMIT - 100:
        ch_msg = ch_msg[:DISCORD_CHAR_LIMIT - 100] + '[...truncated...]'

    for guild in bot.guilds:
        if isinstance(ch_name, str):
            for channel in guild.text_channels + guild.forum_channels:
                threads = channel.threads
                for thread in threads:
                    if thread.name.lower() == ch_name.lower():
                        try:
                            retval = await thread.send('[r8GPT] ' + ch_msg)

                        except Exception as e:
                            ex_msg = f'Exception in scan_world_state/send_ch_msg(1): {e}'
                            print(ex_msg)
                            retval = -1

                        log_msg(ch_msg)
                        return retval

                if channel.name.lower() == ch_name.lower():
                    try:
                        retval = await channel.send('[r8GPT] ' + ch_msg)

                    except Exception as e:
                        ex_msg = f'Exception in scan_world_state/send_ch_msg(2): {e}'
                        print(ex_msg)
                        retval = -1

                    log_msg(ch_msg)
                    return retval
        else:
            try:
                retval = await ch_name.send('[r8GPT] ' + ch_msg)

            except Exception as e:
                ex_msg = f'Exception in scan_world_state/send_ch_msg channel name [{ch_name}] type error: {e}'
                print(ex_msg)
                retval = -1

            log_msg(ch_msg)
            return retval

    print(f"[Warning] thread / channel {ch_name} not found.")
    return -1


async def strike_alert_msgs(target_channel, tid=None, update_message=None):
    # Strike out alert messages for a particular train or the entire channel
    if tid:  # This is a specific set of messages to delete
        if update_message:
            await send_ch_msg(target_channel, update_message)
            await asyncio.sleep(.5)
            log_msg(update_message)
        for msg in alert_messages[tid]:  # Change previous alerts
            strike_it = False
            if RED_SQUARE in msg.content:
                new_content = msg.content.replace(RED_SQUARE, "").strip()
                strike_it = True
            elif RED_EXCLAMATION in msg.content:
                new_content = msg.content.replace(RED_EXCLAMATION, "").strip()
                strike_it = True
            if strike_it:
                # Don't double-strikethrough
                if not (new_content.startswith("~~") and new_content.endswith("~~")):  # noqa
                    new_content = f"~~{new_content}~~"

                try:
                    await msg.edit(content=new_content)
                    await asyncio.sleep(.5)

                except discord.Forbidden:
                    print(f"Missing permissions to edit message ID {msg.id}.")
                except discord.HTTPException as e:
                    print(f"Failed to edit message ID {msg.id}: {e}")

                await msg.edit(content=new_content)
        del alert_messages[tid]
        return
    else:  # We are removing (striking out) all messages in the channel
        for guild in bot.guilds:
            for channel in guild.text_channels + guild.forum_channels:
                if channel.name == target_channel:
                    strike_it = False
                    async for message in channel.history(limit=100):
                        if RED_SQUARE in message.content:
                            new_content = message.content.replace(RED_SQUARE, "").strip()
                            strike_it = True
                        elif RED_EXCLAMATION in message.content:
                            new_content = message.content.replace(RED_EXCLAMATION, "").strip()
                            strike_it = True
                        elif GREEN_CIRCLE in message.content:
                            new_content = message.content.replace(GREEN_CIRCLE, "").strip()
                            strike_it = True
                        elif AXE in message.content:
                            new_content = message.content.replace(AXE, "").strip()
                            strike_it = True

                        if strike_it:
                            # Don't double-strikethrough
                            if not (new_content.startswith("~~") and new_content.endswith("~~")):  # noqa
                                new_content = f"~~{new_content}~~"
                            strike_it = False

                            try:
                                await message.edit(content=new_content)
                                await asyncio.sleep(.5)

                            except discord.Forbidden:
                                print(f"Missing permissions to edit message ID {message.id}.")
                            except discord.HTTPException as e:
                                print(f"Failed to edit message ID {message.id}: {e}")


@bot.slash_command(name='crew', description=f"Crew a train")
@option("symbol", description="Train symbol", required=True)
# NOTE: This command must be executed within a forum thread
async def crew(ctx: discord.ApplicationContext, symbol: str):
    global last_world_datetime

    thread = ctx.channel
    thread_id = ctx.channel.id
    forum_channel = thread.parent
    tag_to_add = discord.utils.find(lambda t: t.name.lower() == CREWED_TAG.lower(), forum_channel.available_tags)
    tag_to_remove = discord.utils.find(lambda t: t.name.lower() == AVAILABLE_TAG.lower(), forum_channel.available_tags)
    if not tag_to_add or not tag_to_remove:
        await ctx.respond(f'[r8GPT] **ERROR**: Tag `{CREWED_TAG}` and/or {AVAILABLE_TAG} not found in this forum.'
                          , ephemeral=True)
        return
    current_tags = thread.applied_tags or []
    if tag_to_add in current_tags:
        await ctx.respond(f'This job is already marked `{tag_to_add.name}` - unable to crew.', ephemeral=True)
        return
    try:
        await ctx.respond(f'Attempting to crew train {symbol}', ephemeral=True)
        tid = find_tid(symbol, curr_trains)
        if tid != -1:
            if curr_trains[tid].engineer.lower() == 'none':
                if player_crew_train(curr_trains, tid, ctx.author.mention, ctx.author.display_name, thread_id,
                                     last_world_datetime) < 0:
                    await ctx.respond(f'**UNABLE TO CREW; You are currently listed as crewing'
                                      f' [{players[ctx.author.mention].train_symbol}]**', ephemeral=True)
                    return
                if tag_to_add not in current_tags:
                    current_tags.append(tag_to_add)
                if tag_to_remove in current_tags:
                    current_tags.remove(tag_to_remove)
                msg = f'{curr_trains[tid].last_time_moved} {ctx.author.display_name} crewed {curr_trains[tid].symbol}'
                await thread.edit(applied_tags=current_tags)
                log_msg(msg)
                await send_ch_msg(CH_LOG, msg)
                r8gptDB.add_event(curr_trains[tid].last_time_moved, ctx.author.display_name,
                                  'CREW', symbol, event_db)
                r8gptDB.save_db(DB_FILENAME, event_db)
                await thread.send(msg)
            else:
                await ctx.respond(f'**UNABLE TO CREW, Train {symbol} shows '
                                  f'crewed by {curr_trains[tid].engineer}**', ephemeral=True)
        else:
            await ctx.respond(f'**UNABLE TO CREW, Train {symbol} not found**')
    except discord.Forbidden:
        await ctx.respond('[r8GPT] **ERROR**: I do not have permission to edit this thread.', ephemeral=True)
    except Exception as e:
        await ctx.respond(f'[r8GPT] **ERROR**: {e}', ephemeral=True)


@bot.slash_command(name='tie_down', description=f"Tie down a train")
@option("location", description="Tie-down location", required=True)
async def tie_down(ctx: discord.ApplicationContext, location: str):
    thread = ctx.channel
    if not isinstance(thread, discord.Thread) or not isinstance(thread.parent, discord.ForumChannel):
        await ctx.respond('This command must be used inside a forum thread.', ephemeral=True)
        return
    forum_channel = thread.parent
    tag_to_add = discord.utils.find(lambda t: t.name.lower() == AVAILABLE_TAG.lower(), forum_channel.available_tags)
    tag_to_remove = discord.utils.find(lambda t: t.name.lower() == CREWED_TAG.lower(), forum_channel.available_tags)
    if not tag_to_add or not tag_to_remove:
        await ctx.respond(f'[r8GPT] **ERROR**: Tag `{CREWED_TAG}` and/or `{AVAILABLE_TAG}` not found in this forum.'
                          , ephemeral=True)
    current_tags = thread.applied_tags or []
    if tag_to_remove not in current_tags:
        await ctx.respond(f'Tag **{tag_to_remove.name}** is not currently applied.', ephemeral=True)
        return
    try:
        await ctx.respond(f'Attempting to tie down', ephemeral=True)
        if ctx.author.mention in players:
            tid = players[ctx.author.mention].train_id
            orig_engineer = curr_trains[tid].engineer
            # Clear info from train record
            curr_trains[tid].engineer = 'none'
            curr_trains[tid].discord_id = None
            curr_trains[tid].job_thread = None
            del players[ctx.author.mention]  # Remove this player record
            if tag_to_add not in current_tags:
                current_tags.append(tag_to_add)
            if tag_to_remove in current_tags:
                current_tags.remove(tag_to_remove)
            msg = (f'{curr_trains[tid].last_time_moved} {ctx.author.display_name} tied down train '
                   f'{curr_trains[tid].symbol} at {location}')
            await thread.send(msg)
            await send_ch_msg(CH_LOG, msg)
            await thread.edit(applied_tags=current_tags)
            log_msg(msg)
            r8gptDB.add_event(curr_trains[tid].last_time_moved, ctx.author.display_name,
                              'TIED_DOWN', curr_trains[tid].symbol, event_db)
            r8gptDB.save_db(DB_FILENAME, event_db)
            if tid in watched_trains:
                # This train has a watch on it - time to remove, and strike-thru previous alert messages
                msg = (f' {GREEN_CIRCLE} {last_world_datetime} **TIED DOWN**: Train {curr_trains[tid].symbol}'
                       f' ({tid}) has been tied down by {orig_engineer}')
                await strike_alert_msgs(CH_ALERT, tid, msg)
                await asyncio.sleep(.5)
                del watched_trains[tid]  # No longer need to watch

            return
        else:
            await ctx.respond(f'**ERROR** Unable to tie-down: '
                              f'You are not listed as crew on any train.', ephemeral=True)

    except discord.Forbidden:
        await ctx.respond('[r8GPT] does not have permission to edit this thread.', ephemeral=True)
    except Exception as e:
        await ctx.respond(f'[r8GPT] Unexpected error: {e}', ephemeral=True)


@bot.slash_command(name='complete', description=f"Mark a job complete")
@option("symbol", description="Train symbol", required=True)
@option('notes', description='completion notes', required=False)
# NOTE: This command must be executed within a forum thread
async def complete(ctx: discord.ApplicationContext, symbol: str, notes: str):
    thread = ctx.channel
    if not isinstance(thread, discord.Thread) or not isinstance(thread.parent, discord.ForumChannel):
        await ctx.respond('This command must be used inside a forum thread.', ephemeral=True)
        return
    forum_channel = thread.parent
    tag_to_add = discord.utils.find(lambda t: t.name.lower() == COMPLETED_TAG.lower(), forum_channel.available_tags)
    tag1_to_remove = discord.utils.find(lambda t: t.name.lower() == CREWED_TAG.lower(), forum_channel.available_tags)
    tag2_to_remove = discord.utils.find(lambda t: t.name.lower() == AVAILABLE_TAG.lower(), forum_channel.available_tags)
    if not tag_to_add or not tag1_to_remove or not tag2_to_remove:
        await ctx.respond(f'[r8GPT] **ERROR**: Tag `{CREWED_TAG}` and/or `{AVAILABLE_TAG}` and/or {COMPLETED_TAG}'
                          f' not found in this forum.', ephemeral=True)
        return
    current_tags = thread.applied_tags or []
    if tag_to_add in current_tags:
        await ctx.respond(f'This job is already marked `{tag_to_add.name}` - unable to change.', ephemeral=True)
        return
    try:
        await ctx.respond(f'Attempting to mark {symbol} as complete.', ephemeral=True)
        if ctx.author.mention in players:
            tid = players[ctx.author.mention].train_id
            orig_engineer = curr_trains[tid].engineer
            # Clear info from train record
            curr_trains[tid].engineer = 'None'
            curr_trains[tid].discord_id = None
            curr_trains[tid].job_thread = None
            del players[ctx.author.mention]  # Remove this player record
            if tag_to_add not in current_tags:
                current_tags.append(tag_to_add)
            if tag1_to_remove in current_tags:
                current_tags.remove(tag1_to_remove)
            if tag2_to_remove in current_tags:
                current_tags.remove(tag2_to_remove)
            msg = (f'{curr_trains[tid].last_time_moved} {ctx.author.display_name} marked train '
                   f'{curr_trains[tid].symbol} {COMPLETED_TAG}')
            if notes:
                msg += f'. Notes: {notes}'
            await thread.send(msg)
            await thread.edit(applied_tags=current_tags)
            log_msg(msg)
            await send_ch_msg(CH_LOG, msg)
            r8gptDB.add_event(curr_trains[tid].last_time_moved, ctx.author.display_name,
                              'MARKED_COMPLETE', curr_trains[tid].symbol, event_db)
            r8gptDB.save_db(DB_FILENAME, event_db)
            if tid in watched_trains:
                # This train has a watch on it - time to remove, and strike-thru previous alert messages
                msg = (f' {GREEN_CIRCLE} {last_world_datetime} **POWERED DOWN**: Train {curr_trains[tid].symbol}'
                       f' ({tid}) has been tied down by {orig_engineer}')
                await strike_alert_msgs(CH_ALERT, tid, msg)
                await asyncio.sleep(.5)
                del watched_trains[tid]  # No longer need to watch

            return
        else:
            await ctx.respond(f'Unable to mark as complete; are you sure you are clocked in?', ephemeral=True)
    except discord.Forbidden:
        await ctx.respond('[r8GPT] **ERROR**: I do not have permission to edit this thread.', ephemeral=True)
    except Exception as e:
        await ctx.respond(f'[r8GPT] **ERROR**: {e}', ephemeral=True)


@bot.slash_command(name="r8list", description="List trains")
@option('list_type', description='type of list (ai, player, idle, stuck)', required=True)
async def r8list(ctx: discord.ApplicationContext, list_type: str):
    msg = ''
    if list_type.lower() == 'player':
        for player in players:
            tid = players[player].train_id
            if players[player].train_symbol != curr_trains[tid].symbol:
                msg += (f'{players[player].discord_name} :'
                        f' **Inconsistent lead unit** // Orig leader: {players[player].train_symbol} // '
                        f' Curr leader: {curr_trains[tid].symbol} //')
            else:
                msg += f'{players[player].discord_name} : {curr_trains[tid].symbol}'
            msg += f' [{tid}] # {curr_trains[tid].lead_num}, Units: {curr_trains[tid].num_units}\n'

    else:
        for tid in curr_trains:
            if list_type.lower() == 'ai':
                if curr_trains[tid].engineer.lower() == 'ai':
                    msg += (f'{curr_trains[tid].symbol} [{tid}] # {curr_trains[tid].lead_num},'
                            f' Units: {curr_trains[tid].num_units}\n')
            elif list_type.lower() == 'stuck':
                if tid in watched_trains:
                    td = last_world_datetime - curr_trains[tid].last_time_moved
                    msg += f'{curr_trains[tid].engineer}'
                    msg += (f' : {curr_trains[tid].symbol} [{tid}] # {curr_trains[tid].lead_num},'
                            f' # {curr_trains[tid].lead_num}, Units: {curr_trains[tid].num_units}, Stopped for: {td},'
                            f' DLC {location(curr_trains[tid].route_1, curr_trains[tid].track_1)}\n')
            else:
                if curr_trains[tid].engineer.lower() == 'none':
                    msg += (f'{curr_trains[tid].symbol} [{tid}] # {curr_trains[tid].lead_num},'
                            f' Units: {curr_trains[tid].num_units}\n')
    if len(msg) < 1:
        msg = f'No {list_type} trains found.'
    if len(msg) > DISCORD_CHAR_LIMIT:
        tf = open(TMP_FILENAME, 'w')
        tf.write(msg)
        tf.close()
        await ctx.response.send_message(file=discord.File(TMP_FILENAME), ephemeral=True)
    else:
        await ctx.respond(msg, ephemeral=True)
    # await ctx.respond(msg, ephemeral=True)


@bot.slash_command(name='train_info', description="Display info of individual train")
@option('tid', required=True, description='Train ID')
async def train_info(ctx: discord.ApplicationContext, tid: int):
    if tid in curr_trains:
        msg = curr_trains[tid]
    else:
        msg = f'Train {tid} not found.'
    await ctx.respond(msg, ephemeral=True)


@bot.slash_command(name='consist_info', description="Display symbols of all cars in train")
@option('tid', required=True, description='Train ID')
async def consist_info(ctx: discord.ApplicationContext, tid: int):
    if tid in curr_trains:
        msg = '`'
        count = 1
        for car in curr_trains[tid].consist:
            msg += f'{count} : {car.dest_tag} | {car.filename.split(".")[0]}\n'
            count += 1
        msg += '`'
    else:
        msg = f'Train {tid} not found.'
    if len(msg) > DISCORD_CHAR_LIMIT:
        tf = open(TMP_FILENAME, 'w')
        tf.write(msg)
        tf.close()
        await ctx.response.send_message(file=discord.File(TMP_FILENAME), ephemeral=True)
    else:
        await ctx.respond(msg, ephemeral=True)


@bot.slash_command(name="check_symbol", description="Check for existence of a train symbol")
@option('symbol', description='symbol', required=True)
async def check_symbol(ctx: discord.ApplicationContext, symbol: str):
    msg = ''
    for tid in curr_trains:
        if curr_trains[tid].symbol == symbol:
            msg += (f'({tid}) {curr_trains[tid].symbol} [#{curr_trains[tid].lead_num}] : '
                    f'{location(curr_trains[tid].route_1, curr_trains[tid].track_1)}\n')
    if len(msg) < 1:
        msg = f'Train {symbol} not found.'
    await ctx.respond(msg, ephemeral=True)


@tasks.loop(seconds=SCAN_TIME)
async def scan_world_state():
    global last_world_datetime
    global last_worlds_save_modified_time  # designated global to keep track between calls

    # Check for initial startup
    if len(curr_trains) == 0:  # No trains means we need to read initial state
        last_worlds_save_modified_time = os.stat(SAVENAME).st_mtime  # Time
        last_world_datetime = update_world_state(curr_trains)
        msg = (f'{last_world_datetime} **--> r8gpt ({VERSION}) INITIALIZING NEW WORLD STATE <--** '
               f'Total number of trains: {train_count("all", curr_trains, watched_trains)} '
               f'(AI trains: {train_count("ai", curr_trains, watched_trains)},'
               f' player trains: {train_count("player", curr_trains, watched_trains)}) ')
        print(msg)
        await send_ch_msg(CH_LOG, msg)
        await strike_alert_msgs(CH_ALERT)  # Get rid of any chaff from previous alerts

    # Check for server reboot
    elif (os.stat(SAVENAME).st_mtime - last_worlds_save_modified_time) > REBOOT_TIME:
        msg = '**Apparent server reboot** : Re-syncing train states'
        # Look for and archive player trains and capture existing player records
        player_updates = list()
        for player in players:
            player_updates.append([players[player].discord_id, players[player].discord_name,
                                   players[player].train_symbol, players[player].train_id, players[player].job_thread])
        msg += f'\nFound {len(player_updates)} players crewing trains - repopulating their info:'
        for player in player_updates:
            msg += f'\n{player[1]} : {player[2]} [{player[3]}]'
        print(msg)
        await send_ch_msg(CH_LOG, msg)
        await asyncio.sleep(.5)
        players.clear()
        # Repopulate trains
        last_worlds_save_modified_time = os.stat(SAVENAME).st_mtime  # Time
        last_world_datetime = update_world_state(curr_trains)
        # Re-add players
        for player in player_updates:
            tid = find_tid(player[2], curr_trains)
            if tid < 0:     # Current train symbol is not found; perhaps lead loco is 'backwards' or train was removed
                if player[3] in curr_trains:
                    tid = player[3]
                    msg = (f'Invalid player {player[1]} train id returned for find_tid({player[2]}) '
                           f'so resorting to archived tid of {player[3]}')
                else:
                    tid = -1    # Can't find this train, so prevent from trying to crew it
                    msg = (f'Train {player[2]}[{player[3]}] not found;'
                           f' removing crew status for player {player[1]}')
                    # Send message in job thread notifying player of the problem
                    player_msg = (f'{player[0]}, during a server reboot your job status for {player[2]} was lost.'
                                  f' Please notify staff (former TID = {player[3]}).')
                    forum_thread = await bot.fetch_channel(player[4])
                    await send_ch_msg(forum_thread, player_msg)
                    await asyncio.sleep(.5)
                    if player[3] in watched_trains:
                        # This train has a watch on it - time to remove, and strike-thru previous alert messages
                        # We are a bit redundant here as the server restart handler will strike through all messages,
                        # but we also want to clear out the watched_trains entry.
                        remove_msg = (
                            f' {GREEN_CIRCLE} {last_world_datetime} **SERVER HICCUP**: Train {player[2]}'
                            f' ({tid}) has been removed after a server restart.')
                        await strike_alert_msgs(CH_ALERT, player[3], remove_msg)
                        await asyncio.sleep(.5)
                        del watched_trains[player[3]]  # No longer need to watch
                print(msg)
                await send_ch_msg(CH_LOG, msg)
                await asyncio.sleep(.5)
            if tid > 0:
                player_crew_train(curr_trains, tid, player[0], player[1], player[4],
                                  last_world_datetime)
        player_updates.clear()
        watched_trains.clear()
        msg = (f'{last_world_datetime} **--> r8gpt ({VERSION}) INITIALIZING NEW WORLD STATE <--** '
               f'Total number of trains: {train_count("all", curr_trains, watched_trains)} '
               f'(AI trains: {train_count("ai", curr_trains, watched_trains)},'
               f' player trains: {train_count("player", curr_trains, watched_trains)}) ')
        print(msg)
        await send_ch_msg(CH_LOG, msg)
        await asyncio.sleep(.5)
        await strike_alert_msgs(CH_ALERT)  # Get rid of any chaff from previous alerts

    #
    # Begin scanning world saves
    #
    # Check time stamp on world save file for an updated version
    if os.stat(SAVENAME).st_mtime != last_worlds_save_modified_time:
        # Updated world save found
        last_worlds_save_modified_time = os.stat(SAVENAME).st_mtime
        last_trains = curr_trains.copy()  # Archive our current set of trains for comparison
        last_world_datetime = update_world_state(curr_trains)  # Update the trains dictionary

        # Check to see if any trains have been deleted
        nbr_ai_removed = 0
        trains_removed = list()
        for tid in last_trains:
            if tid not in curr_trains:
                trains_removed.append(tid)
                nbr_ai_removed += 1
                eng_name = last_trains[tid].engineer
                msg = f'{last_world_datetime} Train removed: {last_trains[tid].symbol} [{eng_name}] ({tid})'
                await send_ch_msg(CH_LOG, msg)
                await asyncio.sleep(.5)
                print(msg)
                if tid in watched_trains:
                    msg = (f' {AXE} {last_world_datetime} **TRAIN DELETED**:'
                           f' [{last_trains[tid].engineer}] {last_trains[tid].symbol} ({tid}) has been deleted.')
                    await strike_alert_msgs(CH_ALERT, tid, msg)
                    await asyncio.sleep(.5)
                    del watched_trains[tid]  # No longer need to watch

        # Run through each player symbol and check that the symbol to tid correspondence hasn't changed
        # Also, populate player / job info on new train dict
        for pid in players:
            for tid in curr_trains:
                if players[pid].train_symbol.lower() == curr_trains[tid].symbol.lower():
                    if players[pid].train_id != curr_trains[tid].train_id:
                        msg = f'Player {players[pid].discord_name} train [{players[pid].train_symbol} has changed ID '
                        msg += f'from {players[pid].train_id} to {curr_trains[tid].train_id}. Updating player record.'
                        players[pid].train_id = curr_trains[tid].train_id
                        await send_ch_msg(CH_LOG, msg)
                        await asyncio.sleep(.5)
                    curr_trains[tid].discord_id = players[pid].discord_id
                    curr_trains[tid].engineer = players[pid].discord_name
                    curr_trains[tid].job_thread = players[pid].job_thread
                else:
                    for car in curr_trains[tid].consist:
                        if players[pid].train_symbol.lower() == car.dest_tag.lower():
                            msg = f'Found player train {players[pid].discord_name} : {players[pid].train_symbol}'
                            msg += f' but not on lead loco - perhaps they have switched leaders(?)'
                            await send_ch_msg(CH_LOG, msg)
                            await asyncio.sleep(.5)
                            if players[pid].train_id != curr_trains[tid].train_id:  # Verify this action #
                                msg = f'Changing ID of {players[pid].discord_name} train [{players[pid].train_symbol}'
                                msg += f' from {players[pid].train_id} to {curr_trains[tid].train_id}.'
                                players[pid].train_id = curr_trains[tid].train_id
                                await send_ch_msg(CH_LOG, msg)
                                await asyncio.sleep(.5)
                            curr_trains[tid].discord_id = players[pid].discord_id
                            curr_trains[tid].engineer = players[pid].discord_name
                            curr_trains[tid].job_thread = players[pid].job_thread
                # Else what if we can't find that symbol?

        nbr_ai_moving = 0
        nbr_player_moving = 0
        nbr_ai_stopped = 0
        nbr_ai_added = 0
        nbr_player_stopped = 0

        for tid in curr_trains:
            # Check for new trains
            if tid not in last_trains:
                nbr_ai_added += 1
                eng_name = curr_trains[tid].engineer
                msg = f'{last_world_datetime} Train spawned: {curr_trains[tid].symbol} [{eng_name}] ({tid})'
                await send_ch_msg(CH_LOG, msg)
                await asyncio.sleep(.5)
                print(msg)

            # Check for moving AI or player trains
            elif (curr_trains[tid].engineer.lower() != 'none' and not  # Ignore static and special tags
            any(tag in curr_trains[tid].symbol.lower() for tag in IGNORED_TAGS)):
                if (curr_trains[tid].route_1 != last_trains[tid].route_1
                        or curr_trains[tid].route_2 != last_trains[tid].route_2
                        or curr_trains[tid].track_1 != last_trains[tid].track_1
                        or curr_trains[tid].track_2 != last_trains[tid].track_2
                        or abs(curr_trains[tid].dist_1 - last_trains[tid].dist_1) > DISTANCE_JITTER
                        or abs(curr_trains[tid].dist_2 - last_trains[tid].dist_2) > DISTANCE_JITTER):
                    # train HAS MOVED since last update
                    if curr_trains[tid].engineer.lower() == 'ai':
                        nbr_ai_moving += 1
                    else:
                        nbr_player_moving += 1

                    if tid in watched_trains:
                        # This train has a watch on it - time to remove, and strike-thru previous alert messages
                        msg = (f' {GREEN_CIRCLE} {last_world_datetime} **ON THE MOVE**: Train {curr_trains[tid].symbol}'
                               f' ({tid}) is now on the move after'
                               f' {last_world_datetime - last_trains[tid].last_time_moved}.')
                        await strike_alert_msgs(CH_ALERT, tid, msg)
                        await asyncio.sleep(.5)
                        del watched_trains[tid]  # No longer need to watch
                elif (curr_trains[tid].route_1 == last_trains[tid].route_1
                      and curr_trains[tid].route_2 == last_trains[tid].route_2
                      and curr_trains[tid].track_1 == last_trains[tid].track_1
                      and curr_trains[tid].track_2 == last_trains[tid].track_2
                      and abs(curr_trains[tid].dist_1 - last_trains[tid].dist_1) < DISTANCE_JITTER
                      and abs(curr_trains[tid].dist_2 - last_trains[tid].dist_2) < DISTANCE_JITTER):
                    # train HAS NOT MOVED since last update
                    if curr_trains[tid].engineer.lower() == 'ai':
                        nbr_ai_stopped += 1
                    else:
                        nbr_player_stopped += 1
                    td = last_world_datetime - last_trains[tid].last_time_moved
                    if (curr_trains[tid].engineer.lower() == 'ai' and td > timedelta(minutes=AI_ALERT_TIME) or
                            curr_trains[tid].engineer.lower() != 'ai' and td > timedelta(minutes=PLAYER_ALERT_TIME)):
                        # The time this train has been stopped is large enough to alert
                        if tid not in watched_trains:  # First alert
                            watched_trains[tid] = [curr_trains[tid].last_time_moved, 1]
                            log_msg(f'Added {tid}: {curr_trains[tid].symbol} to watched trains')
                            alert_msg = f' {RED_SQUARE} {last_world_datetime} **POSSIBLE STUCK TRAIN**: '
                            alert_msg += (f' [{curr_trains[tid].engineer}] {curr_trains[tid].symbol} ({tid})'
                                          f' has not moved for {td}, '
                                          f'DLC {location(curr_trains[tid].route_1, curr_trains[tid].track_1)}.')
                            alert_messages[tid].append(await send_ch_msg(CH_ALERT, alert_msg))
                            await asyncio.sleep(.5)
                            if curr_trains[tid].engineer.lower() != 'ai':
                                player_msg = (
                                    f'{curr_trains[tid].engineer}: You are currently crewing {curr_trains[tid].symbol},'
                                    f' yet your train has not moved for at least {td}. Should you tie down?')
                                forum_thread = await bot.fetch_channel(curr_trains[tid].job_thread)
                                alert_messages[tid].append(await send_ch_msg(forum_thread, player_msg))
                                await asyncio.sleep(.5)
                        elif ((curr_trains[tid].last_time_moved - watched_trains[tid][0])
                              // watched_trains[tid][1] > timedelta(minutes=REMINDER_TIME)):
                            watched_trains[tid][1] += 1
                            alert_msg = (f' {RED_EXCLAMATION} {last_world_datetime}'
                                         f' **STUCK TRAIN REMINDER # {watched_trains[tid][1] - 1}**: ')
                            alert_msg += (f'[{curr_trains[tid].engineer}] {curr_trains[tid].symbol} ({tid})'
                                          f' has not moved for {td}, '
                                          f'DLC {location(curr_trains[tid].route_1, curr_trains[tid].track_1)}.')
                            alert_messages[tid].append(await send_ch_msg(CH_ALERT, alert_msg))
                            await asyncio.sleep(.5)
                            if curr_trains[tid].engineer.lower() != 'ai':
                                player_msg = (
                                    f'{curr_trains[tid].engineer}: You are currently crewing {curr_trains[tid].symbol},'
                                    f' yet your train has not moved for at least {td}. Should you tie down?')
                                forum_thread = await bot.fetch_channel(curr_trains[tid].job_thread)
                                alert_messages[tid].append(await send_ch_msg(forum_thread, player_msg))
                                await asyncio.sleep(.5)
                        else:
                            pass  # We have already notified at least once, now backing off before another notice
                    print(f'[{curr_trains[tid].engineer}] {curr_trains[tid].symbol} ({tid}) has not moved for {td}, '
                          f'DLC {location(curr_trains[tid].route_1, curr_trains[tid].track_1)}')
                    curr_trains[tid].last_time_moved = last_trains[tid].last_time_moved
                    curr_trains[tid].job_thread = last_trains[tid].job_thread
                else:
                    print(f'something odd in comparing these two:\n{curr_trains[tid]}\n{last_trains[tid]}')

        msg = (f'{last_world_datetime} Summary: AI ({nbr_ai_moving}M, {nbr_ai_stopped}S, +{nbr_ai_added}, '
               f'-{nbr_ai_removed}) | Player ({nbr_player_moving}M, {nbr_player_stopped}S) | '
               f'Watched ({len(watched_trains)})')

        await send_ch_msg(CH_LOG, msg)
        await asyncio.sleep(.5)
        print(msg)



@tasks.loop(seconds=10)
async def scan_detectors():
    global detector_files
    global detector_file_time

    detector_files = glob.glob(os.path.join(AEI_PATH, "*"))
    for file in detector_files:
        # Grab timestamp of file save (only way to get any kind of timing)
        src_mtime = os.path.getmtime(file)
        if src_mtime > detector_file_time:
            detector_file_time = src_mtime
            formatted_time = datetime.fromtimestamp(src_mtime).strftime('%Y-%m-%d %H:%M:%S')
            tree = ET.parse(file)
            root = tree.getroot()
            report = parseAEI(formatted_time, root)
            detector_reports[report.name].append(report)
            defects = list()
            for unit in report.units:
                if unit.defect.lower() != 'all_ok':
                    defects.append([unit.sequence, unit.defect])
            if len(defects) > 0:
                defect_msg = ''
                for defect in defects:
                    defect_msg += f'{defect[1]} : {defect[0]}'
            else:
                defect_msg = 'None'
            msg = (f'[{report.timestamp}] {report.name} : {report.symbol} | {report.speed} mph |'
                   f' {report.axles} axles | Defects: {defect_msg}')
            for pid in players:
                if players[pid].train_symbol.lower() in report.symbol.lower():
                    # Send report to job thread
                    forum_thread = await bot.fetch_channel(players[pid].job_thread)
                    await send_ch_msg(forum_thread, msg)
                    await asyncio.sleep(.5)
            log_msg(msg)
            await send_ch_msg(CH_DETECTOR, msg)
            await asyncio.sleep(.5)


@bot.event
async def on_ready():
    global event_db

    print(f"[{datetime.now()}] {bot.user} starting r8gpt v{VERSION}")
    with open(LOG_FILENAME, 'w') as fp:
        fp.write('r8gpt log started\n')
    event_db = r8gptDB.load_db(DB_FILENAME)
    scan_world_state.start()
    scan_detectors.start()


bot.run(BOT_TOKEN)
