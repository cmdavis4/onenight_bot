from slacker import Slacker
from slackclient import SlackClient
import time
from time import time

TOKEN = 'xoxb-30024975425-8gAM9q9u8EeD852FbO6j6gbt'
ONENIGHT_BOT_NAME = 'onenight_bot'

def user_id_to_dm_channel(user_id):
    return 'D' + user_id[1:]

class Game():

    def __init__(self):
        self.players = []

class OneNightState():

    def __init__(self):
        self.web = Slacker(TOKEN)
        self.sc = SlackClient(TOKEN)
        uid_response = self.web.users.list().body['members']
        self.uid_dict = {user_dict['name']: user_dict['id'] for user_dict in uid_response}
        self.game_in_progress = False
        self.onenight_channel_id = [x['id'] for x in self.web.channels.list().body['channels']
                                    if x['name'] == 'onenight'][0]
        self.onenight_bot_name = ONENIGHT_BOT_NAME
        self.onenight_bot_token = '<@%s>' % self.uid_dict[self.onenight_bot_name]
        self.process_message = self.nongame_process_message
        self.sc.rtm_connect()
        self.process_message = self.nongame_process_message

    def listen(self, timeout=None):
        self.is_listening = True
        t0 = time()
        while self.is_listening and (time() - t0 < timeout if timeout is not None else True):
            self.process_events()

    def process_events(self):
        events = self.sc.rtm_read()
        for event in events:
            if (event['type'] == 'message'):
                print(event)
                self.process_message(event)


    def nongame_process_message(self, data):
        if data['channel'] == self.onenight_channel_id:
            # If the bot gets a message in the onenight channel
            if data['text'].startswith(self.onenight_bot_token):
                body = data['text'][len(self.onenight_bot_token):]
                if 'start game' in body.lower() and not self.game_in_progress:
                    self.game_in_progress = True
                    print(self.game_in_progress)
                    self.game()

    def signup_process_message(self, data):
        if data['channel'] == self.onenight_channel_id:
            if data['user'] != self.uid_dict[self.onenight_bot_name]:
                self.game.players.append(data['user'])

    def game(self):
        self.game = Game()
        self.web.chat.post_message(self.onenight_channel_id,
                                     'The game is starting, if you are joining say something in the next ten seconds!',
                                     as_user=True)
        self.process_message = self.signup_process_message
        self.listen(10)
        self.game.players = list(set(self.game.players))
        print(self.game.players)
        self.web.chat.post_message(self.onenight_channel_id,
                                     '%s users are playing' % len(self.game.players),
                                     as_user=True)

if __name__ == '__main__':
    state = OneNightState()
    state.listen()





