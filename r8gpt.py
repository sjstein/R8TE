import asyncio
import discord
from discord.ext import tasks
from discord import option
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
from r8gptInclude import WORLDSAVE_PATH, DB_FILENAME, LOG_FILENAME, AI_ALERT_TIME, PLAYER_ALERT_TIME, BOT_TOKEN, \
    CH_LOG, CH_ALERT, CREWED_TAG
import r8gptDB


# Necessary Bot intents
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

SAVENAME = WORLDSAVE_PATH + '/Auto Save World.xml'
DIESEL_ENGINE = 'US_DieselEngine'
event_db = list()



class Car:
    def __init__(self, filename, unit_type, route, track, node, dist, reverse, weight,
                 dest_tag, unit_number, hazmat_tag):
        self.filename = filename
        self.unit_type = unit_type
        self.route = route
        self.track = track
        self.node = node
        self.dist = dist
        self.reverse = reverse
        self.weight = weight
        self.dest_tag = dest_tag
        self.unit_number = unit_number
        self.hazmat_tag = hazmat_tag

    def __str__(self):
        return str(f'fname: {self.filename}, type: {self.unit_type}, route: {self.route}, track: {self.track}, '
                   f'node: {self.node}, dist: {self.dist}, reverse: {self.reverse}, weight: {self.weight}, '
                   f'dest_tag: {self.dest_tag}, unit_number: {self.unit_number}, hazmat: {self.hazmat_tag}')


class Cut:
    def __init__(self, train_id, is_ai, direction, speed_limit, prev_signal, consist):
        self.train_id = train_id
        self.is_ai = is_ai
        self.direction = direction
        self.speed_limit = speed_limit
        self.prev_signal = prev_signal
        self.consist = consist

    def __str__(self):
        return str(f'ID: {self.train_id}, AI: {self.is_ai}, dir: {self.direction}, spd limit {self.speed_limit},'
                   f'prev signal: {self.prev_signal}, # cars: {len(self.consist)} ')


class Train:
    def __init__(self, id_number, symbol, lead_num, train_type, num_units, engineer, latest_update_time, route, track, dist):
        self.id_number = id_number      # Unique ID
        self.symbol = symbol            # Train tag symbol
        self.lead_num = lead_num        # Lead loco number
        self.train_type = train_type    # freight, passenger
        self.num_units = num_units      # Number of locos + cars total
        self.engineer = engineer        # AI, player, none
        self.latest_update_time = latest_update_time    # Last time this train was tracked
        self.route = route
        self.track = track
        self.dist = dist

    def __str__(self):
        return str(f'ID: {self.id_number}\nSymbol: {self.symbol}\nLead#: {self.lead_num}\nType: {self.train_type}\n'
                   f'Number of cars:{self.num_units}\nEngineer: {self.engineer}\nRoute: {self.route}\n'
                   f'Track: {self.track}\nDist: {self.dist}\nLast Update: {self.latest_update_time}')


def parse_train_loader(root):
    cuts = list()
    for t in root.iter('TrainLoader'):
        train_id = t.find('trainID').text
        was_ai = t.find('TrainWasAI').text
        direction = t.find('DispatchTrainDirection').text
        speed_limit = t.find('ManuallyAppliedSpeedLimitMPH').text
        prev_signal = t.find('PreviousSignalInstruction').text
        units = list()
        unitLoader = t.find('unitLoaderList')
        for rail_vehicle in unitLoader.iter('RailVehicleStateClass'):
            file_name = rail_vehicle.find('rvXMLfilename').text
            unit_type = rail_vehicle.find('unitType').text
            if len(rail_vehicle.find("currentRoutePrefix")) > 1:
                route_prefix = (rail_vehicle.find('currentRoutePrefix')[0].text,
                                rail_vehicle.find('currentRoutePrefix')[1].text)
                track_index = (rail_vehicle.find('currentTrackSectionIndex')[0].text,
                               rail_vehicle.find('currentTrackSectionIndex')[1].text)
                start_node = (rail_vehicle.find('startNodeIndex')[0].text,
                              rail_vehicle.find('startNodeIndex')[1].text)
                distance = (rail_vehicle.find('distanceTravelledInMeters')[0].text,
                            rail_vehicle.find('distanceTravelledInMeters')[1].text)
                reverse = (rail_vehicle.find('reverseDirection')[0].text,
                           rail_vehicle.find('reverseDirection')[1].text)
            else:
                route_prefix = rail_vehicle.find('currentRoutePrefix')[0].text
                track_index = rail_vehicle.find('currentTrackSectionIndex')[0].text
                start_node = rail_vehicle.find('startNodeIndex')[0].text
                distance = rail_vehicle.find('distanceTravelledInMeters')[0].text
                reverse = rail_vehicle.find('reverseDirection')[0].text
            load_weight = rail_vehicle.find('loadWeightUSTons').text
            dest_tag = rail_vehicle.find('destinationTag').text
            unit_number = rail_vehicle.find('unitNumber').text
            hazmat_tag = rail_vehicle.find('hazmatPlacardIndex').text
            units.append(Car(file_name, unit_type, route_prefix, track_index, start_node, distance, reverse, load_weight,
                             dest_tag, unit_number, hazmat_tag))
        cuts.append(Cut(train_id, was_ai, direction, speed_limit, prev_signal, units.copy()))
        units.clear()
    return cuts


idleTrains = dict()
idleTrains2 = dict()
aiTrains = dict()
aiTrains2 = dict()
playerTrains = dict()
playerTrains2 = dict()
player_list = dict()
nbr_player_moving = 0
last_modified = 0
global fp


def update_world_state(ai_trains, player_trains, idle_trains):
    tree = ET.parse(SAVENAME)
    root = tree.getroot()
    world_save_datetime = datetime.strptime(root.find('date').text.split('.')[0], '%Y-%m-%dT%H:%M:%S')
    trains = parse_train_loader(root)
    for train in trains:
        if train.consist[0].unit_type == DIESEL_ENGINE:  # We are only interested in consists with lead locos
            tid = train.train_id
            tag = train.consist[0].dest_tag
            nbr = train.consist[0].unit_number
            rp = train.consist[0].route
            ts = train.consist[0].track
            dist = train.consist[0].dist
            if 'amtrak' in train.consist[0].filename.lower():
                train_type = 'Passenger'
            else:
                train_type = 'Freight'
            if train.is_ai.lower() == 'true':
                ai_trains[tid] = Train(tid, tag, nbr, train_type, len(train.consist), 'AI',
                                       world_save_datetime, rp, ts, dist)
            elif tid in {value: key for key, value in player_list.items()}:
                player_id = [key for key, val in player_list.items() if val == tid]
                player_trains[tid] = Train(tid, tag, nbr, train_type, len(train.consist),
                                           player_id[0], world_save_datetime, rp, ts, dist)
            else:
                idle_trains[tid] = Train(tid, tag, nbr, train_type, len(train.consist),
                                         'None', world_save_datetime, rp, ts, dist)
        else:
            # First car is not a locomotive, so not a valid train
            pass
    return world_save_datetime


def find_player_train(train_tag):
    for train in idleTrains:
        if idleTrains[train].symbol == train_tag:
            return train
    return -1


def add_player_train(train_id, player_id):
    if train_id not in player_list:
        player_list[player_id] = train_id
        playerTrains[train_id] = idleTrains[train_id]
        playerTrains[train_id].engineer = player_id
        del idleTrains[train_id]


def del_player_train(train_id, player_id):
    if player_id in player_list and player_list[player_id] == train_id:
        del player_list[player_id]
        idleTrains[train_id] = playerTrains[train_id]
        idleTrains[train_id].engineer = 'None'
        del playerTrains[train_id]


def log_msg(msg):
    global fp

    fp = open(LOG_FILENAME,'a')
    fp.write(msg + '\n')
    fp.close()


bot = discord.Bot(intents=intents)

# clock_in command
@bot.slash_command(name='clock_in', description=f"Clock in for a job")
@option("symbol", description="Train symbol", required=True)
async def clock_in(ctx: discord.ApplicationContext, symbol: str):
    thread = ctx.channel
    if not isinstance(thread, discord.Thread) or not isinstance(thread.parent, discord.ForumChannel):
        await ctx.respond("❌ This command must be used inside a forum thread.", ephemeral=True)
        return
    forum_channel = thread.parent
    matching_tag = next((tag for tag in forum_channel.available_tags if tag.name.lower() == CREWED_TAG.lower()), None)
    if not matching_tag:
        await ctx.respond(f"❌ Tag '{CREWED_TAG}' not found in this forum.", ephemeral=True)
        return
    current_tag_ids = thread.applied_tags or []
    if matching_tag in current_tag_ids:
        await ctx.respond(f"ℹ️ Tag **{matching_tag.name}** is already applied.", ephemeral=True)
        return
    new_tags = current_tag_ids + [matching_tag]
    try:
        await ctx.respond(f"Attempting to clock in for {symbol}", ephemeral=True)
        ret = find_player_train(symbol)
        if ret != -1:
            add_player_train(ret, ctx.author.mention)
            await thread.edit(applied_tags=new_tags)
            msg = (f"[{playerTrains[ret].latest_update_time}] {ctx.author.display_name} crewed {symbol} [{ret}],"
                   f" thread set to {CREWED_TAG}")
            log_msg(msg)
            r8gptDB.add_event(playerTrains[ret].latest_update_time, ctx.author.display_name,
                              'CLOCK_IN', symbol, event_db)
            r8gptDB.save_db(DB_FILENAME, event_db)
        else:
            msg = f"⚠️ symbol {symbol} not found"
        await thread.send(msg)
    except discord.Forbidden:
        await ctx.respond("❌ I don't have permission to edit this thread.", ephemeral=True)
    except Exception as e:
        await ctx.respond(f"⚠️ Unexpected error: {e}", ephemeral=True)


# clock_out command
@bot.slash_command(name='clock_out', description=f"Clock out from a job")
async def clock_out(ctx: discord.ApplicationContext):
    thread = ctx.channel
    if not isinstance(thread, discord.Thread) or not isinstance(thread.parent, discord.ForumChannel):
        await ctx.respond("❌ This command must be used inside a forum thread.", ephemeral=True)
        return
    forum_channel = thread.parent
    matching_tag = next((tag for tag in forum_channel.available_tags if tag.name.lower() == CREWED_TAG.lower()), None)
    if not matching_tag:
        await ctx.respond(f"❌ Tag '{CREWED_TAG}' not found in this forum.", ephemeral=True)
        return
    current_tag_ids = thread.applied_tags or []
    if matching_tag not in current_tag_ids:
        await ctx.respond(f"ℹ️ Tag **{matching_tag.name}** is not currently applied.", ephemeral=True)
        return
    new_tags = [tid for tid in current_tag_ids if tid != matching_tag]
    try:
        await ctx.respond(f"attempting to clock out...", ephemeral=True)
        for train in playerTrains:
            if playerTrains[train].engineer == ctx.author.mention:
                await thread.edit(applied_tags=new_tags)
                del_player_train(train, ctx.author.mention)
                msg = (f"[{idleTrains[train].latest_update_time}] {ctx.author.display_name} clocked out from train "
                       f"{idleTrains[train].symbol}, {CREWED_TAG} tag removed from thread.")
                await thread.send(msg)
                log_msg(msg)
                r8gptDB.add_event(idleTrains[train].latest_update_time, ctx.author.display_name,
                                  'CLOCK_OUT', idleTrains[train].symbol, event_db)
                r8gptDB.save_db(DB_FILENAME, event_db)
                return
        else:
            ctx.respond(f"⚠️ Unable to clock out; are you sure you are clocked in?", ephemeral=True)

    except discord.Forbidden:
        await ctx.respond("❌ I don't have permission to edit this thread.", ephemeral=True)
    except Exception as e:
        await ctx.respond(f"⚠️ Unexpected error: {e}", ephemeral=True)


@bot.slash_command(name="list_ai", description="List current AI trains")
async def list_ai(ctx: discord.ApplicationContext):
    msg = ''
    for train in aiTrains:
        msg += f'[{aiTrains[train].symbol}], Lead# {aiTrains[train].lead_num}, Units: {aiTrains[train].num_units}\n'
    await ctx.respond(msg, ephemeral=True)


@bot.slash_command(name="list_idle", description="List current AI trains")
async def list_idle(ctx: discord.ApplicationContext):
    msg = ''
    for train in idleTrains:
        msg += (f'[{idleTrains[train].symbol}], Lead# {idleTrains[train].lead_num}, '
                f'Units: {idleTrains[train].num_units}\n')
    await ctx.respond(msg, ephemeral=True)


@bot.slash_command(name="list_player", description="List current AI trains")
async def list_player(ctx: discord.ApplicationContext):
    msg = ''
    for train in playerTrains:
        msg += (f'[{playerTrains[train].symbol}], Lead# {playerTrains[train].lead_num}, '
                f'Units: {playerTrains[train].num_units}\n')
    await ctx.respond(msg, ephemeral=True)


@tasks.loop(seconds=30)
async def scan_world_state():
    global last_modified
    global fp

    async def send_ch_msg(ch_name, ch_msg):
        """
        Send messages to discord channel
        :param ch_name: name of discord channel to write message to
        :param ch_msg: Message content
        :return: 0 if successful, -1 if error
        """
        if ch_msg.lower() == 'none':
            return 0

        for guild in bot.guilds:
            for channel in guild.text_channels + guild.forum_channels:
                threads = channel.threads
                for thread in threads:
                    if thread.name.lower() == ch_name.lower():
                        # write to matching thread name
                        await thread.send('[r8GPT] ' + ch_msg)
                        log_msg(msg)
                        return 0

                if channel.name.lower() == ch_name.lower():
                    # Write to a matching channel name
                    await channel.send('[r8GPT] ' + ch_msg)
                    log_msg(msg)
                    return 0
        print(f"[Warning] thread / channel {ch_name} not found.")
        return -1

    if len(idleTrains) == 0:    # No idle trains means we need to read initial state
        last_modified = os.stat(SAVENAME).st_mtime
        last_world_datetime = update_world_state(aiTrains, playerTrains, idleTrains)
        msg = (f'Loading first world save created on {last_world_datetime}, '
               f'AI trains found: {len(aiTrains)}, '
               f'Idle trains found: {len(idleTrains)}\n-----')
        await send_ch_msg(CH_LOG, msg)
        
    if os.stat(SAVENAME).st_mtime != last_modified:     # Has file timestamp changed since last iteration?
        last_modified = os.stat(SAVENAME).st_mtime
        last_world_datetime = update_world_state(aiTrains2, playerTrains2, idleTrains2)

        # Check to see if any trains have been deleted
        nbr_ai_removed = 0
        nbr_player_removed = 0
        ai_trains_removed = list()
        player_trains_removed = list()
        for trainID in aiTrains:
            if trainID not in aiTrains2:
                ai_trains_removed.append(trainID)
        for trainID in playerTrains:        # Currently this will never be true as the player_train functions mess with the playerTrains structure
            if trainID not in playerTrains2:
                player_trains_removed.append(trainID)

        for tid in ai_trains_removed:
            nbr_ai_removed += 1
            msg = f'Train removed: [AI] {aiTrains[tid].symbol} ({tid})'
            await send_ch_msg(CH_LOG, msg)
            print(msg)
            del aiTrains[tid]

        for tid in player_trains_removed:
            nbr_player_removed += 1
            msg = f'Train removed: [{playerTrains[tid].engineer}] {playerTrains[tid].symbol} ({tid})'
            await send_ch_msg(CH_LOG, msg)
            print(msg)
            del playerTrains[tid]

        nbr_ai_moving = 0
        nbr_player_moving = 0
        nbr_ai_stopped = 0
        nbr_ai_added = 0
        nbr_player_stopped = 0
        nbr_player_added = 0

        # check AI train status
        for trainID in aiTrains2:
            if trainID in aiTrains:
                if aiTrains2[trainID].symbol != aiTrains[trainID].symbol:
                    print(f'TRAIN RE-TAGGED: {trainID} has changed tags since last update '
                          f'({aiTrains[trainID].symbol} -> {aiTrains2[trainID].symbol}); Updating record.')
                    aiTrains[trainID] = aiTrains2[trainID]
                elif aiTrains2[trainID].route != aiTrains[trainID].route \
                        or aiTrains2[trainID].track != aiTrains[trainID].track \
                        or aiTrains2[trainID].dist != aiTrains[trainID].dist:
                    # AI train HAS MOVED since last update
                    nbr_ai_moving += 1
                    aiTrains[trainID].latest_update_time = aiTrains2[trainID].latest_update_time
                elif aiTrains2[trainID].route == aiTrains[trainID].route \
                        and aiTrains2[trainID].track == aiTrains[trainID].track \
                        and aiTrains2[trainID].dist == aiTrains[trainID].dist:
                    # AI train HAS NOT MOVED since last update
                    nbr_ai_stopped += 1
                    td = aiTrains2[trainID].latest_update_time - aiTrains[trainID].latest_update_time
                    msg = ''
                    if td > timedelta(minutes=AI_ALERT_TIME):
                        msg = f'**POSSIBLE STUCK TRAIN**: '
                        msg += f'[AI] {aiTrains2[trainID].symbol} ({trainID}) has not moved for {td}, '
                        msg += f'Location: {aiTrains[trainID].route} / {aiTrains[trainID].track}\n-----'
                        await send_ch_msg(CH_ALERT, msg)
                    print(f'[AI] {aiTrains2[trainID].symbol} ({trainID}) has not moved for {td}, '
                          f'Location: {aiTrains[trainID].route} / {aiTrains[trainID].track}')
                else:
                    print(f'something odd in comparing these two:\n{aiTrains[trainID]}\n{aiTrains2[trainID]}')
            else:
                nbr_ai_added += 1
                print(f'TRAIN SPAWNED: {aiTrains2[trainID].symbol} ({trainID})')
                aiTrains[trainID] = aiTrains2[trainID]

        # Check player train status
        for trainID in playerTrains2:
            if trainID in playerTrains:
                if playerTrains2[trainID].symbol != playerTrains[trainID].symbol:
                    print(f'PLAYER TRAIN RE-TAGGED: {trainID} has changed tags since last update '
                          f'({playerTrains[trainID].symbol} -> {playerTrains2[trainID].symbol}); Updating record.')
                    playerTrains[trainID] = playerTrains2[trainID]

                elif playerTrains2[trainID].route != playerTrains[trainID].route \
                        or playerTrains2[trainID].track != playerTrains[trainID].track \
                        or playerTrains2[trainID].dist != playerTrains[trainID].dist:
                    # player train HAS MOVED since last update
                    nbr_player_moving += 1
                    playerTrains[trainID].latest_update_time = playerTrains2[trainID].latest_update_time

                elif playerTrains2[trainID].route == playerTrains[trainID].route \
                        and playerTrains2[trainID].track == playerTrains[trainID].track \
                        and playerTrains2[trainID].dist == playerTrains[trainID].dist:
                    # Player train HAS NOT MOVED since last update
                    nbr_player_stopped += 1
                    td = playerTrains2[trainID].latest_update_time - playerTrains[trainID].latest_update_time
                    if td > timedelta(minutes=PLAYER_ALERT_TIME):
                        msg = f'**POSSIBLE STUCK TRAIN**: '
                        msg += (f'[{playerTrains2[trainID].engineer}] {playerTrains2[trainID].symbol} ({trainID})'
                                f' has not moved for {td}, Location: {playerTrains2[trainID].route} / '
                                f'{playerTrains2[trainID].track}\n-----')
                        await send_ch_msg(CH_ALERT, msg)
                    print(f'[Player: {playerTrains2[trainID].engineer}] {playerTrains2[trainID].symbol} ({trainID}) '
                          f'has not moved for {td}'
                          f' Location: {playerTrains[trainID].route} / {playerTrains[trainID].track}')

                else:
                    print(f'something odd in comparing these two:\n{playerTrains[trainID]}\n{playerTrains2[trainID]}')

            else:
                nbr_player_added += 1
                print(f'TRAIN SPAWNED: {playerTrains2[trainID][1]} ({trainID})')
                playerTrains[trainID] = playerTrains2[trainID]
        msg = f'Updating world from {last_world_datetime}\n'
        msg += (f'AI Trains: {nbr_ai_moving} moving, {nbr_ai_stopped} stopped, {nbr_ai_removed} removed, '
                f'{nbr_ai_added} added.\n')
        msg += (f'Player trains: {nbr_player_moving} moving, {nbr_player_stopped} stopped, '
                f'{nbr_player_removed} removed, {nbr_player_added} added.\n')
        msg += f'Idle trains: {len(idleTrains)} total.\n-----'
        await send_ch_msg(CH_LOG, msg)
        print(f'AI Summary: {nbr_ai_moving} trains moving, {nbr_ai_stopped} stopped, {nbr_ai_removed} removed, {nbr_ai_added} added.')
        print(f'Player summary: {nbr_player_moving} trains moving, {nbr_player_stopped} stopped,'
              f' {nbr_player_added} added.')
        playerTrains2.clear()
        print(playerTrains)
        print('----')


@bot.event
async def on_ready():
    global fp
    global event_db

    print(f"✅ Bot is ready: {bot.user}")
    fp = open(LOG_FILENAME, 'w')     # filepointer to log file
    event_db = r8gptDB.load_db(DB_FILENAME)
    print(event_db)
    scan_world_state.start()

bot.run(BOT_TOKEN)

