import requests, urllib.request, socket
import os
K = os.environ['OPENAI_API_KEY']
def f():
    return requests.post('https://api.openai.com/v1/chat/completions', headers={'Authorization':'Bearer x'})
def g():
    return urllib.request.urlopen('http://example.com')
