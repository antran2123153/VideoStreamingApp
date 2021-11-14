from tkinter import *
import tkinter.messagebox as tkMessageBox
from PIL import Image, ImageTk
import socket, threading, os

from RtpPacket import RtpPacket

class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
	DESCRIBE = 4

	RECIEVEDFRAME = 0
	CURRENT = 0
	PAST = 0
	FRAMEPERSECOND = 0
	statDataRate = 0.0
	
 
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets()
		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0
		self.connectToServer()
		self.frameNbr = 0
		
  
	def createWidgets(self):
		"""Build GUI."""	
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=1, padx=2, pady=2)
				
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=2, padx=2, pady=2)
		
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Stop"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=1, column=3, padx=2, pady=2)

		self.stop = Button(self.master, width=20, padx=3, pady=3)
		self.stop["text"] = "Describe"
		self.stop["command"] = self.describe
		self.stop.grid(row=1, column=5, padx=2, pady=2)
		
		self.label = Label(self.master, height=19)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 

		self.statDataRateLabel = Label(self.master, text="Data Rate (bits/sec) :", justify='left')
		self.statDataRateLabel.grid(row=3, column=1, padx=2, pady=2)
	
		self.statDataRateValueLabel = Label(self.master, text="")
		self.statDataRateValueLabel.grid(row=3, column=2,padx=2, pady=2)


	def updateStatsLabel(self):
		self.statDataRateValueLabel.config(text="{:.2f}".format(self.statDataRate))
	
 
	def exitClient(self):
		"""Teardown button handler."""
		self.sendRtspRequest(self.TEARDOWN)
		if self.frameNbr != 0:
			print("Lossrate: " + str((self.frameNbr-self.RECIEVEDFRAME)/self.frameNbr))		
		self.master.destroy() 
		os.remove("cache-" + str(self.sessionId) + ".jpg") 


	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)
	
 
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
		if self.state == self.READY:
			threading.Thread(target=self.listenRtp).start()
			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)


	def describe(self):
		if self.state:
			self.sendRtspRequest(self.DESCRIBE)
	
 
	def listenRtp(self):		
		"""Listen for RTP packets."""
		while True:
			try:
				data = self.rtpSocket.recv(20480)
				if data:
					rtpPacket = RtpPacket()
					rtpPacket.decode(data)
					
					currFrameNbr = rtpPacket.seqNum()
					print("Current Seq Num: " + str(currFrameNbr))

					self.FRAMEPERSECOND += 1
					if (rtpPacket.timestamp() != self.CURRENT):
						self.CURRENT = rtpPacket.timestamp()
						self.statDataRate = self.FRAMEPERSECOND*len(rtpPacket.getPayload())
						self.FRAMEPERSECOND = 0
					self.updateStatsLabel() 

					self.RECIEVEDFRAME += 1

					if currFrameNbr > self.frameNbr:
						self.frameNbr = currFrameNbr
						self.updateMovie(self.writeFrame(rtpPacket.getPayload()))

			except:
				if self.playEvent.isSet(): 
					self.statDataRate = 0
					self.updateStatsLabel()
					break
			
				if self.teardownAcked == 1:
					self.rtpSocket.shutdown(socket.SHUT_RDWR)
					self.rtpSocket.close()
					break
					
     
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = "cache-" + str(self.sessionId) + ".jpg"
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		return cachename
	
 
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		photo = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image = photo, height=288) 
		self.label.image = photo
		
  
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			tkMessageBox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)
	
 
	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""	
		if requestCode == self.SETUP and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()
			self.rtspSeq += 1
			request = "SETUP {self.fileName} RTSP/1.0"
			request += "\nCSeq: {self.rtspSeq}"
			request += "\nTransport: RTP/UDP; client_port= {self.rtpPort}"
			self.requestSent = self.SETUP
		elif requestCode == self.PLAY and self.state == self.READY:
			self.rtspSeq += 1
			request = "PLAY {self.fileName} RTSP/1.0"
			request += "\nCSeq: {self.rtspSeq}"
			request += "\nSession: {self.sessionId}"
			self.requestSent = self.PLAY
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			self.rtspSeq += 1
			request = 'PAUSE {self.fileName} RTSP/1.0'
			request += "\nCSeq: {self.rtspSeq}"
			request += "\nSession: {self.sessionId}"
			self.requestSent = self.PAUSE
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			self.rtspSeq += 1
			request = "TEARDOWN {self.fileName} RTSP/1.0"
			request += "\nCSeq: {self.rtspSeq}"
			request += "\nSession: {self.sessionId}"
			self.requestSent = self.TEARDOWN
		elif requestCode == self.DESCRIBE and not self.state == self.INIT:
			self.rtspSeq += 1
			request = "DESCRIBE {self.fileName} RTSP/1.0"
			request += "\nCSeq: {self.rtspSeq}"
			request += "\nSession: {self.sessionId}"
			self.requestSent = self.DESCRIBE
		else:
			return
		
		self.rtspSocket.send(request.encode('utf-8'))
		print('\nData sent:\n' + request)
	
 
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			reply = self.rtspSocket.recv(1024)
			if reply: 
				self.parseRtspReply(reply.decode("utf-8"))
			if self.requestSent == self.TEARDOWN:
				self.rtspSocket.shutdown(socket.SHUT_RDWR)
				self.rtspSocket.close()
				break
	
 
	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		lines = data.split('\n')
		seqNum = int(lines[1].split(' ')[1])
		
		if seqNum == self.rtspSeq:
			session = int(lines[2].split(' ')[1])
			if self.sessionId == 0:
				self.sessionId = session
			if self.sessionId == session:
				if int(lines[0].split(' ')[1]) == 200: 
					if self.requestSent == self.SETUP:
						self.state = self.READY
						self.openRtpPort() 
						self.playMovie()
					elif self.requestSent == self.PLAY:
						self.state = self.PLAYING
					elif self.requestSent == self.PAUSE:
						self.state = self.READY
						self.playEvent.set()
					elif self.requestSent == self.TEARDOWN:
						self.state = self.INIT
						self.teardownAcked = 1 
					elif self.requestSent == self.DESCRIBE:
						mediaInfo = lines[3:]
						for part in mediaInfo:
							print(part)
	
 
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.rtpSocket.settimeout(0.5)
		try:
			self.state = self.READY
			self.rtpSocket.bind((self.serverAddr, self.rtpPort))
		except:
			tkMessageBox.showwarning('Unable to Bind', 'Unable to bind PORT={self.rtpPort}')


	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: 
			self.playMovie()

