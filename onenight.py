from slacker import Slacker
from slackclient import SlackClient
import time
import os
from random import shuffle, random, randint
from time import time, sleep
from copy import copy
from collections import Counter
import pickle

# TODO: Set defaults after timeout
# TODO: Pickle roles/settings from previous game
# TODO: Fix edit messages
# TODO: Add quit game ability
# TODO: Add command explanation
# TODO: Add game explanation
# TODO: Abstract reading of player names into standalone function
# FIXME: Add victory message if no one dies
# FIXME: Doppelganger mason doesn't send message
# FIXME: Double message if there's a tie and hunter kills someone who was already voted to die
# FIXME: "Discussion will now last 1 minutes."

with open('token', 'rb') as f:
    config = pickle.load(f)
    TOKEN = config['token']
    ONENIGHT_BOT_NAME = config['bot_name']
    ONENIGHT_CHANNEL_NAME = config['channel_name']
    #  ONENIGHT_BOT_NAME = 'onenight_bot'
    # ONENIGHT_CHANNEL_NAME = 'onenight'

SLEEP_TIME = 10

DEBUG = False

class take_minimum_time():

    def __init__(self, min_time, fuzz=None):
        self.min_time = min_time
        self.fuzz = fuzz
        if self.fuzz is not None:
            assert self.min_time > fuzz

    def __call__(self, f):
        def wrapped_f(*args):
            if self.fuzz is not None:
                fuzzed_min = self.min_time + (random()*2*self.fuzz) - self.fuzz
            else:
                fuzzed_min = self.min_time
            t = time()
            f(*args)
            elapsed = time() - t
            if elapsed < fuzzed_min:
                sleep(fuzzed_min - elapsed)
        return wrapped_f

class OneNightState():

    ALL_ROLES_DEFAULT_DEAL_ORDER = ['werewolf',
                                    'werewolf',
                                    'seer',
                                    'robber',
                                    'troublemaker',
                                    'villager',
                                    'villager',
                                    'villager',
                                    'minion',
                                    'insomniac',
                                    'drunk',
                                    'doppelganger',
                                    'hunter',
                                    'mason',
                                    'mason',
                                    'tanner']

    ALL_ROLES_TURN_ORDER = ['doppelganger',
                            'werewolf',
                            'minion',
                            'mason',
                            'seer',
                            'robber',
                            'troublemaker',
                            'drunk',
                            'insomniac']

    TEAM_DICT = {
        'werewolf': 'werewolf',
        'seer': 'villager',
        'robber': 'villager',
        'troublemaker': 'villager',
        'minion': 'villager',
        'insomniac': 'villager',
        'drunk': 'villager',
        'hunter': 'villager',
        'mason': 'villager',
        'tanner': 'tanner',
        'villager': 'villager'
    }

    def __init__(self, prev_params=(None, 5)):
        self.web = Slacker(TOKEN)
        self.sc = SlackClient(TOKEN)
        uid_response = self.web.users.list().body['members']
        self.names_to_ids = {user_dict['name']: user_dict['id'] for user_dict in uid_response}
        self.ids_to_names = {v: k for k, v in self.names_to_ids.items()}
        self.game_in_progress = False
        self.onenight_channel_id = [x['id'] for x in self.web.channels.list().body['channels']
                                    if x['name'] == ONENIGHT_CHANNEL_NAME][0]
        self.onenight_bot_name = ONENIGHT_BOT_NAME
        self.onenight_bot_token = '<@%s>' % self.names_to_ids[self.onenight_bot_name]
        self.process_message = self.process_message_nongame
        self.doppelganger_role = None
        self.all_players_in_channel = self.web.channels.info(self.onenight_channel_id).body['channel']['members']
        self.user_message_whitelist = self.all_players_in_channel
        user_to_dms_response = self.web.im.list().body['ims']
        self.user_ids_to_dms = {x['user']: x['id'] for x in user_to_dms_response}
        self.dms_to_user_ids = {v: k for k, v in self.user_ids_to_dms.items()}
        self.team_dict = copy(OneNightState.TEAM_DICT)
        print(self.user_message_whitelist)
        available_cards, discussion_time = prev_params
        self.available_cards = (available_cards if available_cards is not None
                                else copy(OneNightState.ALL_ROLES_DEFAULT_DEAL_ORDER))
        self.discussion_time = discussion_time
        self.prev_params = (self.available_cards, self.discussion_time)

    def announce(self, message):
        self.web.chat.post_message(self.onenight_channel_id,
                                     message,
                                     as_user=True)

    def dm(self, user_or_channel, message):
        if user_or_channel[0] == 'U':
            channel = self.user_ids_to_dms[user_or_channel]
        else:
            channel = user_or_channel
        print(channel)
        self.web.chat.post_message(
            channel,
            message,
            as_user=True
        )

    def is_player_in_current_game(self, player_name):
        try:
            retval = self.names_to_ids[player_name] in self.players
        except KeyError:
            retval = False
        return retval

    def is_dm_to_self(self, data):
        return data['channel'][0] == 'D'

    def is_message_in_onenight_channel(self, data):
        return data['channel'] == self.onenight_channel_id

    def get_players_by_starting_role(self, role):
        players = []
        for p, r in self.starting_roles.iteritems():
            if r == role:
                players.append(p)
        return players

    def flush_event_queue(self):
        while len(self.sc.rtm_read()) != 0:
            pass

    def listen(self, timeout=None):
        if self.sc.rtm_connect():
            self.flush_event_queue()
            self.is_listening = True
            t0 = time()
            while self.is_listening and (time() - t0 < timeout if timeout is not None else True):
                self.process_events()
        else:
            raise IOError("Slack connection failed")

    def process_events(self):
        events = self.sc.rtm_read()
        for event in events:
            if (event['type'] == 'message'):
                if event['user'] in self.user_message_whitelist:
                    print(event)
                    self.process_message(event)

    def process_message_seer(self, data):
        if self.is_dm_to_self(data):
            body = data['text'].lower()
            if self.is_player_in_current_game(body):
                name = body
                id = self.names_to_ids[name]
                self.dm(data['channel'], '%s is the %s!' % (name, self.players[id]))
                self.is_listening = False
            elif 'center' in body:
                inds = [0, 1, 2]
                inds.remove(randint(0, 2))
                position_dict = {0: 'left', 1: 'center', 2: 'right'}
                for i in inds:
                    self.dm(data['channel'], 'The %s card is %s' % (position_dict[i], self.roles_on_table[i]))
                self.is_listening = False

    def process_message_robber(self, data):
        if self.is_dm_to_self(data):
            body = data['text'].lower()
            if self.is_player_in_current_game(body):
                id = self.names_to_ids[body]
                new_robber_role = self.players[id]
                self.dm(data['channel'],
                        'You switch cards with %s, and see that you are now the %s.' % (body, new_robber_role))
                self.players[id] = self.players[data['user']]
                self.players[data['user']] = new_robber_role
                self.is_listening = False

    def process_message_troublemaker(self, data):
        if self.is_dm_to_self(data):
            body = data['text'].lower()
            switched_players = body.split(' ').replace(',', '')
            if (len(switched_players) == 2 and
                False not in [self.is_player_in_current_game(p) for p in switched_players]):
                ids = [self.names_to_ids[p] for p in switched_players]
                first_player_role = self.players[ids[0]]
                self.dm(data['channel'],
                        "You switch %s's and %s's cards." % (switched_players[0], switched_players[1]))
                self.players[ids[0]] = self.players[ids[1]]
                self.players[ids[1]] = first_player_role
                self.is_listening = False

    def process_message_doppelganger(self, data):
        if self.is_dm_to_self(data):
            body = data['text'].lower()
            if self.is_player_in_current_game(body):
                id = self.names_to_ids[body]
                self.doppelganger_role = self.players[id]
                self.dm(data['channel'],
                        "You look at %s's card, and see that you are now the %s." % (body, self.doppelganger_role))
                if self.doppelganger_role == 'seer':
                    self.dm(data['channel'], "Reply with a player's name to look at their card (do not @ them), "
                                  "or 'center' to look at two of the cards on the table.")
                    self.process_message = self.process_message_seer
                    self.listen()
                elif self.doppelganger_role == 'robber':
                    self.dm(data['channel'], "Reply with a player's name to switch cards with them (do not @ them.)")
                    self.process_message = self.process_message_robber
                    self.listen()
                elif self.doppelganger_role == 'troublemaker':
                    self.dm(data['channel'], "Reply with the names of the two players whose cards you would "
                                          "like to switch (do not @ them.)")
                    self.process_message = self.process_message_troublemaker
                    self.listen()
                elif self.doppelganger_role == 'drunk':
                    inds = [0, 1, 2]
                    shuffle(inds)
                    position = inds[0]
                    position_dict = {0: 'left', 1: 'center', 2: 'right'}
                    self.dm(data['channel'], 'You switch your card with the %s card' % position_dict[position])
                self.is_listening = False

    def process_message_nongame(self, data):
        if self.is_message_in_onenight_channel(data):
            if data['text'].startswith(self.onenight_bot_token) and not self.game_in_progress:
                body = data['text'][len(self.onenight_bot_token):]
                print(body)
                if 'start game' in body.lower():
                    self.game_in_progress = True
                    print(self.game_in_progress)
                    self.is_listening = False
                    self.game()
                    self.game_in_progress = False
                elif 'add' in body.lower():
                    roles = body.split('add ')[-1].split(', ')
                    for role in roles:
                        if role in OneNightState.ALL_ROLES_DEFAULT_DEAL_ORDER:
                            if self.available_cards.count(role) == OneNightState.ALL_ROLES_DEFAULT_DEAL_ORDER.count(role):
                                self.announce('Max number of %ss have already been added' % role)
                            else:
                                self.available_cards.append(role)
                    self.announce("The cards in play are now:")
                    self.announce('\n'.join(sorted(self.available_cards)))
                elif 'remove' in body.lower():
                    roles = body.split('remove ')[-1].split(', ')
                    for role in roles:
                        if role in OneNightState.ALL_ROLES_DEFAULT_DEAL_ORDER:
                            if role not in self.available_cards:
                                self.announce('All %ss have already been removed.' % role)
                            else:
                                self.available_cards.remove(role)
                    self.announce("The cards in play are now:")
                    self.announce('\n'.join(sorted(self.available_cards)))
                elif 'list roles' in body.lower():
                    self.announce("The cards in play are now:")
                    self.announce('\n'.join(sorted(self.available_cards)))
                elif body.lower().split(':')[-1].strip() == 'sup':
                    self.announce('SUPWITCHU')
                elif 'set time' in body.lower():
                    duration = body.split('set time')[-1].strip()
                    try:
                        self.discussion_time = int(duration)
                        self.prev_params = (self.available_cards, self.discussion_time)
                        self.announce("Discussion will now last %d minutes." % self.discussion_time)
                    except ValueError:
                        pass

    def process_message_signup(self, data):
        if self.is_message_in_onenight_channel(data):
            if data['user'] != self.names_to_ids[self.onenight_bot_name]:
                self.players[data['user']] = None

    def process_message_voting(self, data):
        if self.is_message_in_onenight_channel(data):
            if data['user'] != self.names_to_ids[self.onenight_bot_name]:
                body = data['text'].lower()
                if self.is_player_in_current_game(body) and data['user'] not in self.voting_dict:
                    self.voting_dict[data['user']] = self.names_to_ids[body]

    def role_dispatch(self, role):
        return getattr(self, '%s_turn' % role)()

    def doppelganger_turn(self):
        self.announce("Doppelganger, wake up and look at another player's card. You are now "
                      "that role. If your new role has a night action, do it now.")
        doppelgangers = self.get_players_by_starting_role('doppelganger')
        if len(doppelgangers) == 0:
            sleep(1.5 * SLEEP_TIME)
        else:
            doppelganger = doppelgangers[0]
            self.dm(doppelganger, "Reply with a player's name to look at their card (do not @ them).")
            self.user_message_whitelist = [doppelganger]
            self.process_message = self.process_message_doppelganger
            self.listen()
            self.user_message_whitelist = []
            self.is_listening = False
        if 'minion' in self.roles_in_play:
            self.announce("If you are now a minion, keep your eyes open. Otherwise, close them. "
                          "Werewolves, stick out your thumb so the Doppelganger-Minion can see who you are.")
            if self.doppelganger_role == 'minion':
                werewolves = self.get_players_by_starting_role('werewolf')
                if len(werewolves) == 0:
                    self.dm(self.get_players_by_starting_role('doppelganger')[0],
                            "There are no werewolves.")
                if len(werewolves) == 1:
                    self.dm(self.get_players_by_starting_role('doppelganger')[0],
                            "%s is the only werewolf." % werewolves[0])
                else:
                    self.dm(self.get_players_by_starting_role('doppelganger')[0],
                            "The werewolves are %s and %s." % (werewolves[0], werewolves[1]))
            self.announce("Werewolves, put your thumbs away.")
        self.announce("Doppelganger, close your eyes.")

    def werewolf_turn(self):
        self.announce('Werewolves, wake up and look for other werewolves.')
        werewolves = self.get_players_by_starting_role('werewolf')
        if self.doppelganger_role == 'werewolf':
            werewolves += self.get_players_by_starting_role('doppelganger')[0]
        if len(werewolves) == 0:
            pass
        elif len(werewolves) == 1:
            self.dm(werewolves[0], 'You are the only werewolf, so you get to see a card from the table:')
            inds = [0, 1, 2]
            shuffle(inds)
            inds_dict = {0: 'left', 1: 'center', 2: 'right'}
            self.dm(werewolves[0], 'The %s card is %s.' % (inds_dict[inds[0]], self.roles_on_table[inds[0]]))
        elif len(werewolves) == 2:
            self.dm(werewolves[0], 'The other werewolf is %s!' % self.ids_to_names[werewolves[1]])
            self.dm(werewolves[1], 'The other werewolf is %s!' % self.ids_to_names[werewolves[0]])
        elif len(werewolves) == 3:
            for i in range(3):
                inds = [0, 1, 2]
                inds.remove(i)
                self.dm(werewolves[i], 'The other werewolves are %s and %s.' % (werewolves[inds[0]], werewolves[inds[1]]))
        sleep(SLEEP_TIME)
        self.announce('Werewolves, close your eyes')

    def minion_turn(self):
        self.announce("Minion, wake up. Werewolves, stick out your thumb so the "
                      "Minion can see who you are.")
        minions = self.get_players_by_starting_role('minion')

        if len(minions) == 0:
            pass
        else:
            minion = minions[0]
            werewolves = self.get_players_by_starting_role('werewolf')
            if self.doppelganger_role == 'werewolf':
                werewolves += self.get_players_by_starting_role('doppelganger')[0]
            if len(werewolves) == 0:
                self.dm(minion, "There are no werewolves.")
            elif len(werewolves) == 1:
                self.dm(minion, "%s is the only werewolf." % self.ids_to_names[werewolves[0]])
            elif len(werewolves) == 2:
                self.dm(minion, "The werewolves are %s and %s." % (self.ids_to_names[werewolves[0]], self.ids_to_names[werewolves[1]]))
            elif len(werewolves) == 3:
                self.dm(minion, "The werewolves are %s, %s, and %s." % (self.ids_to_names[werewolves[0]],
                                                                        self.ids_to_names[werewolves[1]],
                                                                        self.ids_to_names[werewolves[2]]))
        sleep(SLEEP_TIME)
        self.announce("Minion, close your eyes.")

    def mason_turn(self):
        self.announce("Masons, wake up and look for other masons.")
        masons = self.get_players_by_starting_role('mason')
        if self.doppelganger_role == 'mason':
            masons += self.get_players_by_starting_role('doppelganger')[0]
        if len(masons) == 0:
            pass
        elif len(masons) == 1:
            self.dm(masons[0], 'You are the only mason!')
        elif len(masons) == 2:
            self.dm(masons[0], 'The other mason is %s!' % self.ids_to_names[masons[1]])
            self.dm(masons[1], 'The other mason is %s!' % self.ids_to_names[masons[0]])
        elif len(masons) == 3:
            for i in range(3):
                inds = [0, 1, 2]
                inds.remove(i)
                self.dm(masons[i], 'The other masons are %s and %s.' % (self.ids_to_names[masons[inds[0]]],
                                                                        self.ids_to_names[masons[inds[1]]]))
        sleep(SLEEP_TIME)
        self.announce("Masons, close your eyes.")
        
    def seer_turn(self):
        self.announce("Seer, wake up. You may look at another player's card or two of the center cards.")
        seers = self.get_players_by_starting_role('seer')
        if len(seers) == 0:
            sleep(SLEEP_TIME)
        else:
            seer = seers[0]
            self.dm(seer, "Reply with a player's name to look at their card (do not @ them), "
                          "or 'center' to look at two of the cards on the table.")
            self.user_message_whitelist = [seer]
            self.process_message = self.process_message_seer
            self.listen()
            self.user_message_whitelist = []
        self.announce("Seer, close your eyes.")

    def robber_turn(self):
        self.announce("Robber, wake up. You may exchange your card with "
                      "another player's card, and then view your new card.")
        robbers = self.get_players_by_starting_role('robber')
        if len(robbers) == 0:
            sleep(SLEEP_TIME)
        else:
            robber = robbers[0]
            self.dm(robber, "Reply with a player's name to switch cards with them (do not @ them.)")
            self.process_message = self.process_message_robber
            self.user_message_whitelist = [robber]
            self.listen()
            self.user_message_whitelist = []
        self.announce("Robber, close your eyes.")

    def troublemaker_turn(self):
        self.announce("Troublemaker, wake up. You may exchange cards "
                      "between two other players.")
        troublemakers = self.get_players_by_starting_role('troublemaker')
        if len(troublemakers) == 0:
            sleep(SLEEP_TIME)
        else:
            troublemaker = troublemakers[0]
            self.dm(troublemaker, "Reply with  the names of the two players"
                                  "whose cards you would like to switch (do not @ them,) "
                                  "formatted as e.g. 'alice, bob'")
            self.user_message_whitelist = [troublemaker]
            self.process_message = self.process_message_troublemaker
            self.listen()
            self.user_message_whitelist = []
        self.announce("Troublemaker, close your eyes.")

    def drunk_turn(self):
        self.announce("Drunk, wake up and exchange your card with a card from the center.")
        drunks = self.get_players_by_starting_role('drunk')
        if len(drunks) == 0:
            pass
        else:
            drunk = drunks[0]
            inds = [0, 1, 2]
            shuffle(inds)
            position = inds[0]
            position_dict = {0: 'left', 1: 'center', 2: 'right'}
            self.dm(drunk, 'You switch your card with the %s card' % position_dict[position])
        sleep(SLEEP_TIME)
        self.announce("Drunk, close your eyes.")

    def insomniac_turn(self):
        self.announce("Insomniac, wake up and look at your card.")
        insomniacs = self.get_players_by_starting_role('insomniac')
        if len(insomniacs) == 0:
            pass
        else:
            insomniac = insomniacs[0]
            self.dm(insomniac, "Your card is now the %s" % self.players[insomniac])
        sleep(SLEEP_TIME)
        self.announce("Insomniac, close your eyes.")
        if 'doppelganger' in self.roles_in_play:
            self.announce("Doppelganger, if you viewed the Insomniac card, wake up and look at your card.")
            doppelgangers = self.get_players_by_starting_role('doppelganger')
            if len(doppelgangers) == 0:
                pass
            elif self.doppelganger_role == 'insomniac':
                doppelganger = doppelgangers[0]
                self.dm(doppelganger, "Your card is now the %s" % self.players[doppelganger])
            sleep(SLEEP_TIME)
            self.announce("Doppelganger, close your eyes.")

    def win_condition(self, kills):
        killed_teams = [self.team_dict[k] for k in kills]
        if 'tanner' in killed_teams:
            self.announce("Tanner wins!")
        if (
            'werewolf' in killed_teams or
            (
                     len(killed_teams) == 0 and
                     'werewolf' not in self.players.values() and
                     self.doppelganger_role != 'werewolf'
            )
           ):
            self.announce("Villagers win!")
        else:
            self.announce("Werewolves win!")

    def game(self):
        self.announce('The game is starting, if you are joining say something in the next ten seconds!')
        self.process_message = self.process_message_signup
        # dm_whitelist is set to include all players in channel
        self.players = {}
        self.listen(10)
        self.user_message_whitelist = []
        # print(self.players)
        players_in_game_str = [self.ids_to_names[x] for x in list(self.players.keys())]

        if not DEBUG:
            if len(self.players) < 3:
                self.announce("There are not enough players to start the game.")
                self.__init__(self.prev_params)
                return
            if len(self.players) > 10:
                self.announce("There are too many players.")
                self.__init__(self.prev_params)
                return
            self.announce(
                    ', '.join(players_in_game_str[:-1]) + ', and ' + players_in_game_str[-1] + ' are playing.')
        if DEBUG:
            if len(self.players) == 0:
                self.announce("Can't have 0 players.")
                self.__init__(self.prev_params)
                return
            self.announce('%s players are playing.' % len(self.players))


        if len(self.available_cards) < len(self.players) + 3 and not DEBUG:
            self.announce("Not enough cards are in play. "
                          "Please add cards until there are at least 3 more than the number of players "
                          "and start a new game.")
            self.__init__(self.prev_params)
            return
        roles_in_play = copy(self.available_cards)
        shuffle(roles_in_play)

        # Trim to correct number of cards
        self.roles_in_play = roles_in_play[:len(self.players) + 3]
        while 'werewolf' not in self.roles_in_play:
            del self.roles_in_play[-1]
            self.roles_in_play.append(roles_in_play.pop())

        self.announce('The following cards are in play:')
        self.announce(', '.join(self.roles_in_play))

        self.announce('Roles will now be assigned!')
        players = list(self.players.keys())
        shuffle(self.roles_in_play)
        shuffle(players)
        for i in range(len(players)):
            player = players[i]
            role = self.roles_in_play[i]
            self.dm(player, 'You are the %s!' % role)
            self.players[player] = role
        self.starting_roles = copy(self.players)
        self.roles_on_table = self.roles_in_play[-3:]
        self.announce('Everyone, close your eyes.')
        for role in OneNightState.ALL_ROLES_TURN_ORDER:
            if role in self.roles_in_play:
                self.role_dispatch(role)

        self.announce("Everyone, wake up!")
        self.announce("You now have %d minutes to discuss!" % self.discussion_time)
        sleep(2 if DEBUG else (60*self.discussion_time) - 10)
        self.announce("There are 10 seconds left in discussion!")
        for i in range(10, 0, -1):
            t = time()
            self.announce("%d..." % i)
            elapsed = time() - t
            if elapsed < 1:
                sleep(1-elapsed)
        self.announce("VOTE NOW! You have 5 seconds to vote! Say the name of the player that you are voting "
                      "to kill in this channel (do not @ them.) Your first vote is what will be counted!")
        self.user_message_whitelist = list(self.players.keys())
        self.process_message = self.process_message_voting
        self.voting_dict = {}
        self.listen(5)
        if len(self.voting_dict) == 0:
            self.announce('No one voted? You guys suck!')
            self.__init__(self.prev_params)
        vote_counts = dict(Counter(list(self.voting_dict.values())))
        most = max(vote_counts.values())
        killed_ids = [k for k in vote_counts if vote_counts[k] == most]
        killed_names = [self.ids_to_names[k] for k in killed_ids]
        self.announce("VOTING IS CLOSED! The results are in...")
        if most == 1:
            self.announce("No one dies!")
            self.killed_roles = []
        else:
            if len(killed_names) == 1:
                killed_message = killed_names[0]
            if len(killed_names) == 2:
                killed_message = killed_names[0] + ' and ' + killed_names[1]
            if len(killed_names) > 2:
                killed_message = ', '.join(killed_names[:-1]) + ', and ' + killed_names[-1]
            self.announce(killed_message + ' will die!!!')
            self.announce("Let's look at their card(s)...")
            killed_roles = []
            for k in killed_ids:
                role = self.players[k]
                self.announce("%s was the %s!" % (self.ids_to_names[k], role))
                if role == 'hunter':
                    hunter_vote = self.voting_dict[k]
                    self.announce("%s voted for %s, so they also die!" % (
                        self.ids_to_names[k], self.ids_to_names[hunter_vote]))
                    hunter_kill = self.players[hunter_vote]
                    self.announce("%s was the %s!" % (self.ids_to_names[hunter_vote], hunter_kill))
                    killed_roles.append(hunter_kill)
                    killed_roles.append(role)
                elif role == 'doppelganger':
                    self.announce("They viewed the %s card!" % self.doppelganger_role)
                    if self.doppelganger_role == 'hunter':
                        hunter_vote = self.voting_dict[k]
                        self.announce("%s voted for %s, so they also die!" % (self.ids_to_names[k], hunter_vote))
                        hunter_kill = self.players[hunter_vote]
                        self.announce("%s was the %s!" % (self.ids_to_names[hunter_vote], hunter_kill))
                        killed_roles.append(hunter_kill)
                    killed_roles.append(self.doppelganger_role)
                else:
                    killed_roles.append(role)
        self.announce("Everyone's cards were as follows:")
        self.announce('\n'.join(["%s: %s" % (self.ids_to_names[p], self.players[p]) for p in players]))
        self.win_condition(killed_roles)
        self.__init__(self.prev_params)
        self.listen()


if __name__ == '__main__':
    state = OneNightState()
    state.listen()
 