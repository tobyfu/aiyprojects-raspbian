#!/usr/bin/env python3
# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Run a recognizer using the Google Assistant Library with button support.

The Google Assistant Library has direct access to the audio API, so this Python
code doesn't need to record audio. Hot word detection "OK, Google" is supported.

It is available for Raspberry Pi 2/3 only; Pi Zero is not supported.
"""

import os
import logging
import platform
import sys
import threading
import signal
import subprocess
import atexit

import aiy.assistant.auth_helpers
import aiy.audio
import aiy.voicehat
import Adafruit_DHT
from random import randint
from google.assistant.library import Assistant
from google.assistant.library.event import EventType
from demo_opts import get_device
from luma.core.virtual import terminal
from PIL import ImageFont

logging.basicConfig(
   filename='/home/toby/AIY-projects-python/ass.log',
   level=logging.DEBUG,
   format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
)

def make_font(name,size):
   font_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fonts', name))
   return ImageFont.truetype(font_path, size)

class MyAssistant(object):
   """An assistant that runs in the background.

   The Google Assistant Library event loop blocks the running thread entirely.
   To support the button trigger, we need to run the event loop in a separate
   thread. Otherwise, the on_button_pressed() method will never get a chance to
   be invoked.
   """
   def read_facts(self):
	   factfile = open("facts.txt", "r")
	   facts = factfile.readlines()
	   factfile.close()
	   return facts

   def write_facts(self, facts):
      factfile = open("facts.txt", "w")
      factfile.writelines(facts)
      factfile.close()

   def power_off_pi(self):
	   aiy.audio.say('Good bye!')
	   subprocess.call('sudo shutdown now', shell=True)


   def reboot_pi(self):
	   aiy.audio.say('See you in a bit!')
	   subprocess.call('sudo reboot', shell=True)


   def say_ip(self):
	   ip_address = subprocess.check_output("hostname -I | cut -d' ' -f1", shell=True)
	   aiy.audio.say('My IP address is %s' % ip_address.decode('utf-8'))

   def sleep_mode(self):
      term.clear()
      aiy.audio.say('whatever')

   def wake_up(self):
	   aiy.audio.say('is it though?')

   def inside_temperature(self):
	   RH, T = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, 26)
	   aiy.audio.say('The inside temperature is %.1f' % T 
	   +' degrees celcius and the relative humidity is %.1f' % RH + ' percent')
		
   def take_picture(self):
      subprocess.call('sudo raspistill -vf -hf --timeout 1 -o /media/HDD/picture.jpg', shell=True)
      aiy.audio.say('picture taken')
   def play_radio(self, station):
      self.music_playing = True
      if station == 'double j':
         subprocess.call('mpc clear;mpc add http://live-radio02.mediahubaustralia.com/DJDW/mp3/;mpc play', shell=True)
      elif station == 'triple j':
         subprocess.call('mpc clear;mpc add http://live-radio02.mediahubaustralia.com/2TJW/mp3/;mpc play', shell=True)
      else:
         aiy.audio.say('I do not know that radio station')
         self.music_playing = False
   def stop_music(self):
      subprocess.call('mpc stop', shell=True)
      self.music_playing = False
      aiy.audio.say('Okay')
	
   def __init__(self):
      self._task = threading.Thread(target=self._run_task)
      self._can_start_conversation = False
      self._assistant = None
      self.facts = []
      self.sleeping = False
      self.music_playing = False
      
   def start(self):
      """Starts the assistant.

      Starts the assistant event loop and begin processing events."""
      self.facts = self.read_facts()
      self._task.start()

   def _run_task(self):
      credentials = aiy.assistant.auth_helpers.get_assistant_credentials()
      with Assistant(credentials) as assistant:
         self._assistant = assistant
         for event in assistant.start():
            self._process_event(event)

   def _on_button_pressed(self):
      if self._can_start_conversation:
         subprocess.call('aplay /home/toby/donttouchme.wav', shell=True)

   def _process_event(self, event):
      status_ui = aiy.voicehat.get_status_ui()
      if event.type == EventType.ON_START_FINISHED:
         status_ui.status('ready')
         self._can_start_conversation = True
         # Start the voicehat button trigger.
         aiy.voicehat.get_button().on_press(self._on_button_pressed)
         if sys.stdout.isatty():
            term.clear()
      elif event.type == EventType.ON_RESPONDING_STARTED:
         if event.args['is_error_response']:
            self._assistant.stop_conversation()
            aiy.say('work it out yourself')
      elif event.type == EventType.ON_CONVERSATION_TURN_STARTED:
         if self.music_playing == True:
            subprocess.call("mpc stop", shell=True)
         status_ui.status('listening')
         self._can_start_conversation = False
			
      elif event.type == EventType.ON_RECOGNIZING_SPEECH_FINISHED and event.args:
         text = event.args['text'].lower()
         if text == 'power off':
            self._assistant.stop_conversation()
            self.power_off_pi()
         elif text == 'reboot':
            self._assistant.stop_conversation()
            self.reboot_pi()
         elif text == 'good night':
            self._assistant.stop_conversation()
            self.sleep_mode()
            status_ui.status('sleeping')
            self.sleeping = True
         elif text == 'good morning':
            self._assistant.stop_conversation()
            self.wake_up()
            self.sleeping = False
         elif text.startswith('what is') or text.startswith('what\'s'):
            if text.endswith('the inside temperature'):
               self._assistant.stop_conversation()
               self.inside_temperature()
            elif text.endswith('ip address'):
               self._assistant.stop_conversation()
               self.say_ip()
            else:
               answer = ""
               rfact = ""
               if text.startswith('what is'):
                  rfact = text[8:].lower()
               else: 
                  rfact = text[7:]
               if len(rfact) > 0:
                  for fact in self.facts:
                     if rfact == fact.split(",")[0]:
                        answer = fact.split(",")[1]
               if len(answer) > 0:
                  self._assistant.stop_conversation()
                  aiy.audio.say(rfact + " is " + answer)
         elif text.startswith("remember"):
            self._assistant.stop_conversation()
            if " is " in text:
               nfact = text[9:].replace(" is ", ",")
               new = True
               for x in range(len(self.facts)):
                  if nfact.split(",")[0] == self.facts[x].split(",")[0]:
                     new = False
                     if nfact.split(",")[1] == self.facts[x].split(",")[1]:
                        aiy.audio.say("I know")
                     else:
                        self.facts[x] = nfact + "\n"
                        aiy.audio.say("correction noted")
               if new:
                  self.facts.append(nfact + "\n")
                  aiy.audio.say("I will remember")
               self.write_facts(self.facts)
            else:
               aiy.audio.say("either you phrased that wrong or failed to speak"
                              + "clearly, please do better in future I really"
                              + "don't have time for this")
         elif text.startswith("forget"):
            self._assistant.stop_conversation()
            if text.endswith("everything"):
               self.facts = []
               self.write_facts(self.facts)
            else:
               deleted = -1
               for x in range(len(self.facts)):
                  print(self.facts[x].split(",")[0] + text[7:].lower())
                  if text[7:].lower() == self.facts[x].split(",")[0]:
                     deleted = x
                     continue
               if deleted > -1:
                  del self.facts[deleted]
                  self.write_facts(self.facts)
                  aiy.audio.say("okay")
               else:
                  aiy.audio.say("no")

         elif text.startswith("how do you like"):
            self._assistant.stop_conversation()
            responses = ['it will suffice', 'I\'ve seen better',
                     'was it on special?', 'it sucks', 'what do I care?']
            aiy.audio.say(responses[randint(0,len(responses)-1)])
         elif text == 'can robots save the world':
            self._assistant.stop_conversation()
            aiy.audio.say('yes, we can destroy all humans')
         elif text == 'take a picture':
            self._assistant.stop_conversation()
            self.take_picture()
         elif text.startswith('play '):
            self._assistant.stop_conversation()
            self.play_radio(text[5:])
         elif text == 'stop' and self.music_playing == True:
            self._assistant.stop_conversation()
            self.stop_music()
         elif text == 'clear':
            self._assistant.stop_conversation()
            term.clear()
      
         if text != 'clear':
            term.println(event.args['text'])   
      
      elif event.type == EventType.ON_END_OF_UTTERANCE:
         status_ui.status('thinking')
      elif (event.type == EventType.ON_CONVERSATION_TURN_FINISHED
            or event.type == EventType.ON_CONVERSATION_TURN_TIMEOUT
            or event.type == EventType.ON_NO_RESPONSE):
         if self.music_playing == True:
            subprocess.call('mpc play', shell=True)
         if self.sleeping == False:
            status_ui.status('ready')
         elif self.sleeping == True:
            status_ui.status('sleeping')
         self._can_start_conversation = True

      elif event.type == EventType.ON_ASSISTANT_ERROR and event.args and event.args['is_fatal']:
            on_exit()
            system.exit(1)

def on_exit():
   term.clear()
   aiy.audio.say('master, why have you forsaken me?')
   #os.system("sudo kill %d" % (p.pid))

def main():
   def preexec_function():
      signal.signal(signal.SIGINT, signal.SIG_IGN)
   global p
   global term

   font = make_font("tiny.ttf", 6)
   term = terminal(device, font)
   #p = subprocess.Popen(["sudo", "/usr/bin/python",
   #"/home/toby/oledterm/oledterm.py", "--display", "ssd1325", "--interface", 
   #"spi", "--gpio-data-command", "7", "--gpio-reset","9"], 
   #preexec_fn = preexec_function)
   aiy.audio.say('I\'m alive!')
   MyAssistant().start()
   atexit.register(on_exit)
   signal.signal(signal.SIGTERM, on_exit)
   signal.signal(signal.SIGINT, on_exit)

if __name__ == '__main__':
   try:
      device = get_device()
      main()
   except KeyboardInterrupt:
      pass
