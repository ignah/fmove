#! /usr/bin/env python3

import signal, os, syslog
import daemon

import tkinter
from tkinter import messagebox, Text, Entry
from tkinter import X
from tkinter import LEFT
from tkinter import RAISED
from tkinter.ttk import Frame, Label, Button
import pynput

import threading
from datetime import datetime
import argparse

class config:

	interval = 30.0
	delta = 1
	lock = False
	lock_position = (0, 0)
	lock_position2 = (0, 0)
	logging = False
	use_terminal = True

	def __init__(self):
		parser = argparse.ArgumentParser(description='fmove v0.19 2022.03.16')
		parser.add_argument('-t', '--use_terminal',
				action='store_true', help='whether window will be used.')
		parser.add_argument('-i', '--interval', type=float, help='interval')
		parser.add_argument('-d', '--delta', type=int, help='delta')
		parser.add_argument('-k', '--lock', type=str, help='XxY')
		parser.add_argument('-p', '--position',
				action='store_true', help='print mouse position')
		parser.add_argument('-l', '--logging',
				action='store_true', help='enable logging')
		args = parser.parse_args()
		self.use_terminal = args.use_terminal == True
		if args.interval:
			self.interval = float(args.interval)
		if args.delta:
			self.delta = int(args.delta)
		if args.lock:
			s = str(args.lock).split('x')
			self.lock = True
			self.lock_position = (int(s[0]), int(s[1]))
		if args.position:
			print(str(pynput.mouse.Controller().position))
			quit()
		if args.logging:
			self.logging = int(args.logging)

class mlistener():

	fmove = None 
	listener = None

	def __init__(self, fmove):
		self.fmove = fmove
	
	def __del__(self):
		if self.listener:
			self.stop()

	def on_mouse_move(self, x, y):
		self.fmove.emit_mouse_move()

	def on_mouse_click(self, x, y, button, pressed):
		if pressed:
			self.fmove.emit_mouse_pressed()

	def start(self):
		if not self.listener:
			self.listener = pynput.mouse.Listener(
					on_move = self.on_mouse_move,
					on_click = self.on_mouse_click)
			self.listener.start()
			self.listener.wait()

	def stop(self):
		self.listener.stop()
		self.listener = None

class fmove:

	term = 0
	syslog_inited = False

	def __init__(self, interval=3, delta=10,
			lock = False, lock_position = (0,0), logging = True):

		self.interval = interval
		self.delta = delta
		self.lock = lock
		self.lock_position = lock_position
		self.lock_position2 = lock_position
		self.logging = logging

		self.mouse_dir = 0
		self.mouse = pynput.mouse.Controller()
		self.screen_size = None

		self.cond = threading.Condition()
		self.thr = threading.Thread(target = self.keep_mouse_move)

		self.fwindow = None
	
	def __del__(self):
		pass

	def start(self):
		self.thr.start()
	
	def join(self):
		return self.thr.join()

	def pause(self):
		self.cond.acquire()
		self.term = 2
		self.cond.notify()
		self.cond.release()

	def resume(self):
		self.cond.acquire()
		self.term = 0
		self.cond.notify()
		self.cond.release()

	def get_mouse_position(self):
		if self.lock:
			return self.lock_position
		return self.mouse.position

	def set_mouse_position(self, pos):
		self.mouse.position = pos

	def set_fwindow(self, fwindow):
		self.fwindow = fwindow

	def get_screen_size(self):
		if self.screen_size:
			return self.screen_size
		if not self.fwindow or not self.fwindow.window:
			w = tkinter.Tk()
			self.screen_size = (w.winfo_screenwidth(), w.winfo_screenheight())
			w.destroy()
		else:
			self.screen_size = self.fwindow.get_screen_size()
		return self.screen_size

	def is_position_in_screen(self, pos):
		ssize = self.get_screen_size()
		return (pos[0] >= 0 and pos[1] >= 0
				and pos[0] < ssize[0] and pos[1] < ssize[1])

	def get_new_position(self, cur_pos, delta):
		new_pos = cur_pos
		if self.mouse_dir == 0:
			new_pos = (cur_pos[0] + delta, cur_pos[1])
		elif self.mouse_dir == 1:
			new_pos = (cur_pos[0], cur_pos[1] + delta)
		elif self.mouse_dir == 2:
			new_pos = (cur_pos[0] - delta, cur_pos[1])
		else:
			new_pos = (cur_pos[0], cur_pos[1] - delta)
		self.mouse_dir += 1
		self.mouse_dir %= 4
		if self.is_position_in_screen(new_pos):
			return new_pos
		return self.get_new_position(cur_pos, delta)

	def mouse_move(self):
		pos = self.get_new_position(self.get_mouse_position(), self.delta)
		self.set_mouse_position(pos)

	def change_lock_position(self):
		if not self.lock:
			self.lock_position2 = self.lock_position
			self.lock_position = self.mouse.position
			if self.logging:
				self.print_log('{:>11}{}, {}'.format('lock: ',
					self.position_to_string(self.lock_position),
					self.position_to_string(self.lock_position2)))
			if self.fwindow and self.fwindow.window:
				self.fwindow.window.event_generate('<<lock_position_changed>>',
					x=self.lock_position[0], y=self.lock_position[1])

	def keep_mouse_move(self):
		listener = mlistener(self)
		listener.start()
		while True:
			self.cond.acquire()
			if self.cond.wait(self.interval):
				self.print_mouse_position('signaled: ')
				if self.term == 0:
					pass # just move!
				if self.term == 1:
					self.cond.release()
					break
				elif self.term == 2:
					self.print_mouse_position('paused: ')
					self.cond.wait()
					self.print_mouse_position('resumed: ')
				elif self.term == 3: # mouse pressed!
					self.change_lock_position()
					self.term = 0
			else:
				self.print_mouse_position('timeouted: ')
				self.mouse_move()
			self.cond.release()
		listener.stop()
	
	def emit_mouse_move(self):
		self.cond.acquire()
		self.term = 0
		self.cond.notify()
		self.cond.release()

	def emit_mouse_pressed(self):
		self.cond.acquire()
		self.term = 3
		self.cond.notify()
		self.cond.release()
	
	def emit_terminate(self):
		self.cond.acquire()
		self.term = 1
		self.cond.notify()
		self.cond.release()

	def syslog_init(self):
		if self.syslog_inited:
			return
		syslog.openlog('fmove', syslog.LOG_PID)
		self.syslog_inited = True
	
	def print_log(self, message):
		if self.fwindow and self.fwindow.window:
			if not self.syslog_inited:
				self.syslog_init()
			syslog.syslog(message)
		else:
			print('{} {}'.format(self.get_now_timestamp(), message))

	def print_mouse_position(self, prefix=''):
		pos = self.mouse.position
		if self.logging:
			self.print_log('{:>11}{}, interval={}, delta={}'.format(
				prefix, self.position_to_string(pos), self.interval, self.delta))
		if self.fwindow and self.fwindow.window:
			self.fwindow.window.event_generate('<<position_changed>>',
					x=pos[0], y=pos[1])

	def get_now_timestamp(self):
		return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

	def position_to_string(self, pos):
		return '({:4d},{:4d})'.format(pos[0], pos[1])

class fwindow():
	def __init__(self, fmove):
		self.fmove = fmove
		self.window = tkinter.Tk()
	
	def get_screen_size(self):
		return (self.window.winfo_screenwidth(), self.window.winfo_screenheight())

	def show(self):
		self.window.title('fmove')
		self.window.geometry('200x240')
		self.window.protocol("WM_DELETE_WINDOW", self.on_window_closing)
		self.window.bind('<<position_changed>>', self.on_position_changed)
		self.window.bind('<<lock_position_changed>>', self.on_lock_position_changed)
		self.window.bind('<Control-c>', self.window_close)

		f = Frame(self.window)
		f.pack(fill=X)
		l = Label(f, text='position', width=10)
		l.pack(side=LEFT, padx=10, pady=5)
		self.label_position = Label(f, text='0,0')
		self.label_position.pack(side=LEFT, padx=2, pady=5)

		f = Frame(self.window)
		f.pack(fill=X)
		l = Label(f, text='interval', width=10)
		l.pack(side=LEFT, padx=10, pady=5)
		entry_interval = Entry(f, width=6)
		entry_interval.insert(0, str(self.fmove.interval))
		entry_interval.pack(side=LEFT, padx=2, pady=5)
		buttonI = Button(f, text='Ok',
				command=lambda: self.on_button_clicked(buttonI, entry_interval),
				width=3)
		buttonI.bid = 5
		buttonI.pack(side=LEFT, padx=0, pady=5)

		f = Frame(self.window)
		f.pack(fill=X)
		l = Label(f, text='delta', width=10)
		l.pack(side=LEFT, padx=10, pady=5)
		entry_delta = Entry(f, width=6)
		entry_delta.insert(0, str(self.fmove.delta))
		entry_delta.pack(side=LEFT, padx=2, pady=5)
		buttonD = Button(f, text='Ok',
				command=lambda: self.on_button_clicked(buttonD, entry_delta),
				width=3)
		buttonD.bid = 6
		buttonD.pack(side=LEFT, padx=0, pady=5)

		f = Frame(self.window)
		f.pack(fill=X)
		t = "Lock"
		if self.fmove.lock:
			t = "Unlock"
		buttonL = Button(f, text=t,
				command=lambda: self.on_button_clicked(buttonL), width=10)
		buttonL.bid = 4
		buttonL.pack(side=LEFT, padx=10, pady=5)

		self.label_lock_position = Label(f, text=str(self.fmove.lock_position))
		self.label_lock_position.pack(side=LEFT, padx=2, pady=5)

		f = Frame(self.window)
		f.pack(fill=X)
		l = Label(f, text='logging', width=10)
		l.pack(side=LEFT, padx=10, pady=5)

		t = "On"
		if self.fmove.logging == True:
			t = "Off"
		buttonG = Button(f, text=t,
				command=lambda: self.on_button_clicked(buttonG), width=9)
		buttonG.bid = 3
		buttonG.pack(side=LEFT, padx=2, pady=5)


		f = Frame(self.window, relief=RAISED, borderwidth=1)
		f.pack(fill=X)
		buttonC = Button(f, text='Pause',
				command=lambda: self.on_button_clicked(buttonC), width=9)
		buttonC.bid = 1
		buttonC.pack(side=LEFT, padx=10, pady=5)
		buttonX = Button(f, text='Exit',
				command=lambda: self.on_button_clicked(buttonX), width=9)
		buttonX.bid = 2
		buttonX.pack(side=LEFT, padx=2, pady=5)

		self.window.mainloop()

	def window_close(self, event = None):
		self.fmove.cond.acquire()
		self.window.destroy()
		self.window = None 
		self.fmove.cond.release()
		self.fmove.emit_terminate()

	def on_window_closing(self):
		if messagebox.askokcancel("Quit", "Do you want to quit?"):
			self.window_close()

	def on_lock_position_changed(self, *text):
		self.label_lock_position['text'] = '{},{}'.format(text[0].x, text[0].y)

	def on_position_changed(self, *text):
		self.label_position['text'] = '{},{}'.format(text[0].x, text[0].y)

	def on_button_clicked(self, button = None, field = None):
		if button.bid == 1: # ctl
			if button['text'] == 'Pause':
				button['text'] = 'Resume'
				self.fmove.pause()
			else:
				button['text'] = 'Pause'
				self.fmove.resume()
		elif button.bid == 2: # exit
			self.window_close()
		elif button.bid == 3: # logging
			if button['text'] == 'Off':
				button['text'] = 'On'
				self.fmove.logging = False
			else:
				button['text'] = 'Off'
				self.fmove.logging = True
		elif button.bid == 4: # lock
			if button['text'] == 'Unlock':
				button['text'] = 'Lock'
				self.fmove.lock = False
			else:
				button['text'] = 'Unlock'
				self.fmove.lock = True
				self.fmove.lock_position = self.fmove.lock_position2
				self.window.event_generate('<<lock_position_changed>>',
						x=self.fmove.lock_position[0],
						y=self.fmove.lock_position[1])
		elif button.bid == 5:
			self.fmove.interval = float(field.get())
		elif button.bid == 6:
			self.fmove.delta = int(field.get())

def signal_handler(signum, frame, fmove=None):
	if signum == signal.SIGINT:
		if fmove:
			fmove.emit_terminate()

def cmain(conf):
	m = fmove(conf.interval, conf.delta,
			conf.lock, conf.lock_position, conf.logging)
	m.start()
	signal.signal(signal.SIGINT,
			lambda signum, frame: signal_handler(signum, frame, m))
	m.join()

def wmain(conf):
	m = fmove(conf.interval, conf.delta,
			conf.lock, conf.lock_position, conf.logging)
	m.start()
	fwin = fwindow(m)
	m.set_fwindow(fwin)
	try:
		fwin.show()
	except KeyboardInterrupt:
		fwin.window_close()
	m.join()


def main():
	conf = config()
	if conf.use_terminal:
		cmain(conf)
	else:
		with daemon.DaemonContext():
			wmain(conf)

if __name__ == '__main__':
	main()
