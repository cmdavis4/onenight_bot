import os
import sys
import pickle

token = raw_input('Bot token: ')
bot_name = raw_input('Bot name: ')
channel_name = raw_input('Channel name: ')

with open('token', mode='wb') as f:
    pickle.dump({
        'token': token,
        'bot_name': bot_name,
        'channel_name': channel_name
    },
                f)
