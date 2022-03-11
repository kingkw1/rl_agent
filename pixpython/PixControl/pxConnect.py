import sys
import threading
import asyncio
import websockets
import json
import enum
import datetime
from queue import Queue
from av.video.frame import VideoFrame
from pyee import AsyncIOEventEmitter

from aiortc import codecs
from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError


class JSKeyCode(enum.Enum):
    tab = 9
    shift = 16
    ctrl = 17
    alt = 18
    left = 37
    up = 38
    right = 39
    down = 40
    zero = 48
    one = 49
    two = 50
    three = 51
    four = 52
    five = 53
    six = 54
    seven = 55
    eight = 56
    nine = 57
    a = 65
    b = 66
    c = 67
    d = 68
    e = 69
    f = 70
    g = 71
    h = 72
    i = 73
    j = 74
    k = 75
    l = 76
    m = 77
    n = 78
    o = 79
    p = 80
    q = 81
    r = 82
    s = 83
    t = 84
    u = 85
    v = 86
    w = 87
    x = 88
    y = 89
    z = 90


class MouseCode(enum.Enum):
    left = 0
    middle = 1
    right = 2


class MessageType(enum.Enum):

	#Control Messages. Range = 0..49.
	IFrameRequest = 0
	RequestQualityControl = 1
	MaxFpsRequest = 2
	AverageBitrateRequest = 3
	StartStreaming = 4
	StopStreaming = 5
	
	#Input Messages. Range = 50..89.
	#Generic Input Messages. Range = 50..59.
	UIInteraction = 50
	Command = 51

	#Keyboard Input Message. Range = 60..69.
	KeyDown = 60
	KeyUp = 61
	KeyPress = 62

	#Mouse Input Messages. Range = 70..79.
	MouseEnter = 70
	MouseLeave = 71
	MouseDown = 72
	MouseUp = 73
	MouseMove = 74
	MouseWheel = 75

	#Touch Input Messages. Range = 80..89.
	TouchStart = 80
	TouchEnd = 81
	TouchMove = 82


#class for receiving audio and video tracks 
class MDisplay():
    def __init__(self, uec):
        self.__tracks = {}
        self.uec = uec

    def addTrack(self, track):
        #track - class:`aiortc.MediaStreamTrack`.
        if track not in self.__tracks:
            self.__tracks[track] = None

    async def start(self):
        for track, task in self.__tracks.items():
            if task is None:
                self.__tracks[track] = asyncio.create_task(self.__run_track(track))
                print('MDisplay Started')

    #main function where the frames are received and processed
    async def __run_track(self, track):
        while True:
            try:
                #convert av.video.frame.VideoFrame to numpy.ndarray
                frame = await track.recv()
                if type(frame) == VideoFrame:
                    #float POSIX timestamp
                    ttime = datetime.datetime.now().timestamp()
                    dframe = frame.to_ndarray(format='bgr24')
                    self.uec.emit('videoframe', (dframe,ttime))
                else:
                    #pass over the av.audio.frame.AudioFrame directly
                    self.uec.emit('audioframe', frame)
                    pass
            except MediaStreamError:
                print('Track Error!!!!!!!!!!!!!!')
                return       

    async def stop(self):
        for task in self.__tracks.values():
            if task is not None:
                task.cancel()
        self.__tracks = {}


#event names 'videoframe' 'datamessage' 'audioframe'
class UEConnect(AsyncIOEventEmitter):
    def __init__(self, address: str, enableVideo=False, enableAudio=False):
        super().__init__()
        self.__address = 'ws://' + address  #signaling server address
        self.__webs = None      #websocket
        self.__peerc = None     #aiortc peer connection
        self.__datac = None     #aiortc data channel
        self.__md = None        #MDisplay
        self.__audio = None     #aiortc audio transceiver
        self.__video = None     #aiortc video transceiver
        self.__inputTask = None #asyncio task for connecting
        self.__dataconnected = False 
        self.__inputQ = Queue() #queue of keyboard mouse inputs to send out
        self.__dataQ = Queue()  #queue of data messages to send out

        self.doVideo = enableVideo
        self.doAudio = enableAudio
        self.stopEvent = threading.Event()  #event to externally stop everything

    #expecting string JSKeyCode enum keyName and bool keyDown for keyboard input
    #for mouse button presses keyName = (MoueCode enum, xLoc, yLoc) and bool keyDown, locations are 0 to 100  float as a percentage of the screen
    #for mouse movement keyName = ('move', xLoc, yLoc) and kyeDown = (deltaX, deltaY),  deltas are -100 to 100  float as a percentage of the screen
    def addInputQ(self, keyName, keyDown) -> None:
        self.__inputQ.put((keyName,keyDown))

    #sends data as a ui interaction for Unreal to handle
    def addDataQ(self, data: str) -> None:
        self.__dataQ.put(data)

    #returns the stats of the peer connection from aiortc
    def getPeerCStats(self) -> dict:
        return self.__peerc.getStats()

    async def connect(self) -> None:
        connectTask = asyncio.create_task(self.__internalConnect())
        await asyncio.create_task(self.__waitOnConnection())
        connectTask.cancel()
        print('Connected!!!!!!!!!!!!!!!!!!!!!!')
        
    #main loop ran from unrealConnect class 
    async def waitLoop(self) -> None:
        print('Waiting Forever')
        while True:
            if self.__inputQ.empty() == False:
                nextInput = self.__inputQ.get_nowait()
                self.__sendInput(nextInput[0], nextInput[1])
                
            #await to open up 
            await asyncio.sleep(0)

            if self.__dataQ.empty() == False:
                nextData = self.__dataQ.get_nowait()
                self.__sendUII(nextData)

            await asyncio.sleep(0)

            if self.stopEvent.is_set():
                break

    #closes everything that the connection uses
    async def closeEverything(self) -> None:
        if self.__webs != None:
            await self.__webs.close()
    
        if self.__peerc != None:
            await self.__peerc.close()

        if self.__md != None:
            await self.__md.stop()

        if self.__inputTask != None:
            self.__inputTask.cancel()

    async def __waitOnConnection(self) -> None:
        while True:
            if self.__dataconnected == False:
                await asyncio.sleep(0.5)
            else:
                break

    async def __waitForMessage(self) -> None:
        if self.__webs != None:
            message = await self.__webs.recv()
            messageD = json.loads(message)
            if 'type' in messageD:
                if messageD['type'] == 'config':
                    pass

                elif messageD['type'] == 'playerCount':
                    await self.__makeOffer()
                
                elif messageD['type'] == 'answer':
                    await self.__gotRTCAnswer(messageD)

                elif messageD['type'] == 'iceCandidate':
                    await self.__gotRTCIce(messageD)

    async def __internalConnect(self) -> None:
        self.__peerc = RTCPeerConnection()
        self.__md = MDisplay(self)

        @self.__peerc.on('track')
        def on_track(track):
            self.__md.addTrack(track)
            print('track added!!')

        @self.__peerc.on('datachannel')
        def on__datachannel(channel):
            print('!!!!!Channel created by Remote: ', channel.label)

        @self.__peerc.on('connectionstatechange')
        def on_connection_state_change():
            print('!!!!!State Changed: ' + self.__peerc.connectionState)

        @self.__peerc.on('iceconnectionstatechange')
        def on_ice_connection_state():
            print('!!!!!Ice Changed: ' + self.__peerc.iceConnectionState)

        @self.__peerc.on('icegatheringstatechange')
        def on_ice_gathering_state():
            print('!!!!!Ice Gathering: ' + self.__peerc.iceGatheringState)

        @self.__peerc.on('signalingstatechange')
        def on_signal_state():
            print('!!!!!Signal Change: ' + self.__peerc.signalingState)

        print('connecting to: ' + self.__address)
        self.__webs = await websockets.connect(self.__address)

        task1 = asyncio.create_task(self.__messageLoop())
        await task1

    async def __messageLoop(self) -> None:
        while True:
            await self.__waitForMessage()

    async def __makeOffer(self) -> None:
        self.__datac = self.__peerc.createDataChannel('cirrus')

        #appears to be no common video codecs from Unreal to the aiortc library without changing the hard coded value in codec init
        #manually changing the level of the h264 codec manually to make things work since it's hard coded in aiortc
        #hickety hack
        codecs.CODECS["video"][2].parameters["profile-level-id"] = "42e034"
        
        if self.doAudio:
            self.__audio = self.__peerc.addTransceiver('audio', 'recvonly')
        if self.doVideo:
            self.__video = self.__peerc.addTransceiver('video', 'recvonly')

        @self.__datac.on('open')
        def on_open():
            print('data channel open')
            self.__dataconnected = True

        @self.__datac.on('close')
        def on_close():
            print('data channel close')

        @self.__datac.on('message')
        def on_message(message):
            #message has \x01 at the start of the message
            decoded = message.decode('utf-8')
            decoded = decoded[1:]
            decoded = decoded.replace(b'\x00'.decode('utf-8'), '')
            self.emit('datamessage', decoded)

        await self.__peerc.setLocalDescription(await self.__peerc.createOffer())
        offerString = json.dumps({'type' : self.__peerc.localDescription.type, 'sdp' : self.__peerc.localDescription.sdp})
        await self.__webs.send(offerString)

    async def __gotRTCAnswer(self, messageD) -> None:
        remoteDescription = RTCSessionDescription(type=messageD['type'], sdp=messageD['sdp'])
        await self.__peerc.setRemoteDescription(remoteDescription)
        await self.__md.start()

    async def __gotRTCIce(self, messageD) -> None:
        can = messageD['candidate']
        parts = can['candidate'].split()

        ff = parts[0][10:]
        cmp = int(parts[1])
        ipp = parts[4]
        pt = int(parts[5])
        pty = int(parts[3])
        ptl = parts[2]
        tp = parts[7]
        iceCan = RTCIceCandidate(component=cmp, foundation=ff, ip=ipp, port=pt, priority=pty, protocol=ptl, type=tp, sdpMid=can['sdpMid'], sdpMLineIndex=can['sdpMLineIndex'])

        await self.__peerc.addIceCandidate(iceCan)

    #sends the ui interaction message out
    def __sendUII(self, msg: str) -> None:
        btemp = [bytes([MessageType.UIInteraction.value])[0]]
        
        lbyt = len(msg).to_bytes(2,'little')
        btemp.append(lbyt[0])
        btemp.append(lbyt[1])

        for char in msg:
            btemp.append(bytes(char, 'utf-8')[0])
            btemp.append(0)
        
        self.__datac.send(bytes(btemp))

    #sends the keyboard mouse input message out
    def __sendInput(self, keyName, keyDown) -> None:
        isKeyboard = False
        isMouse = False

        #determine the type of input by variable type
        isKeyboard = type(keyName) == str 
        isMouse = type(keyName) == tuple

        #send message for keyboard input    
        if isKeyboard:
            try:
                ikey = bytes([JSKeyCode[keyName].value])
            except KeyError:   
                return

            if keyDown:
                btemp = [bytes([MessageType.KeyDown.value])[0]]
            else:
                btemp = [bytes([MessageType.KeyUp.value])[0]]
        
            btemp.append(ikey[0])

            if keyDown:
                btemp.append(0)
       
            self.__datac.send(bytes(btemp))

        #send message for mouse button
        if isMouse:
            mName = keyName[0]
            #percentage of uint16
            mx = int((keyName[1]/100) * 65535)
            my = int((keyName[2]/100) * 65535)
            isMove = mName == 'move'

            if isMove:
                if type(keyDown) != tuple:
                    return
                
                #percentage of int16
                dx = int((keyDown[0] / 50) * 32768)
                dy = int((keyDown[1] / 50) * 32768)
                
                btemp = [bytes([MessageType.MouseMove.value])[0]]
                tLoc = mx.to_bytes(2,'little')
                btemp.append(tLoc[0])
                btemp.append(tLoc[1])
                tLoc = my.to_bytes(2,'little')
                btemp.append(tLoc[0])
                btemp.append(tLoc[1])
                tLoc = dx.to_bytes(2,'little', signed=True)
                btemp.append(tLoc[0])
                btemp.append(tLoc[1])
                tLoc = dy.to_bytes(2,'little', signed=True)
                btemp.append(tLoc[0])
                btemp.append(tLoc[1])

                self.__datac.send(bytes(btemp))


            else:
                try:
                    ikey = bytes([MouseCode[mName].value])
                except KeyError:
                    return
                
                if keyDown:
                    btemp = [bytes([MessageType.MouseDown.value])[0]]
                else:
                    btemp = [bytes([MessageType.MouseUp.value])[0]]
            
                btemp.append(ikey[0])
                tLoc = mx.to_bytes(2,'little')
                btemp.append(tLoc[0])
                btemp.append(tLoc[1])
                tLoc = my.to_bytes(2,'little')
                btemp.append(tLoc[0])
                btemp.append(tLoc[1])

                self.__datac.send(bytes(btemp))