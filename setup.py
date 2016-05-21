import os
import sys
import pickle

token = raw_input('Bot token: ')

with open('token', mode='wb') as f:
    pickle.dump(token, f)
