import threading
import asyncio
import cv2
import json
import time
from typing import Callable, List
import PixControl.pxConnect as pxc
from PixControl.subsystemInterface import *

def _threadStarter(uecon):
    asyncio.set_event_loop(asyncio.new_event_loop())
    uecon.start()

#class designed to handle connection to unreal, send/receive input and data messages
class UEPixClient():
    def __init__(self, address: str, useVideo: bool, useAudio: bool, xRes=1280, yRes=720):
        self.__ueconnect = pxc.UEConnect(address, useVideo, useAudio)
        self.subModuleList = []
        self.callbackDict = {}
        self.__ccounter = 0
        self.__connected = False
        self.__res = (xRes,yRes)
        self.__useV = useVideo
        self.messageFactories = {}
        for MessageClass in InMessageInterface.__subclasses__():
            self.messageFactories[MessageClass.getMessageType()] = MessageClass.loadMessage
            
        #initialize callbacks for received data
        #video frames are tuple numpy.ndarray in bgr24 format, float POSIX timestamp from dataetime when frame was decoded
        @self.__ueconnect.on('videoframe')
        def onvideo(frame):
            for one in self.subModuleList:
                one.onVideo(frame)
        
        @self.__ueconnect.on('datamessage')
        def ondata(data):
            try:
                #checks to see if there is a callback associated with the message
                mdict = json.loads(data)
                cb = self.callbackDict.pop(int(mdict['messageId']), None)

                #creates the message interface object if it has one
                if 'dataType' in mdict:
                    factoryMethod = self.messageFactories.get(mdict['dataType'], None)
                    if callable(factoryMethod):
                        temp = factoryMethod(mdict)
                        if temp != None:
                            mdict = temp
                    
                if callable(cb):
                    cb(mdict)
                else:
                    #call the onData function on all subsystems if there is no callback
                    for one in self.subModuleList:
                        one.onData(mdict)
            except Exception as e:
                print('error decoding!!', e)
                print('data received on error:', data)
                pass
        #audio frames are av.audio.frame.AudioFrame
        @self.__ueconnect.on('audioframe')
        def onaudio(frame):
            for one in self.subModuleList:
                one.onAudio(frame)

    #adds the callback function to the callback dictionary with the same key as the message ID
    def __setupCallback(self, dataD: UERequestDataInterface):
        if callable(dataD.callback):
            self.callbackDict[str(dataD.messageID)] = dataD.callback
            dataD.callback = True
        else:
            dataD.callback = False

    #gets the connection state
    def isConnected(self):
        return self.__connected

    #initializes all clients and adds them to the list of subsystems
    def addSubModules(self, subMods: List[SubsystemInterface]) -> None:
        for one in subMods:
            one.initialize(self)
            self.subModuleList.append(one)

    #stop the connection that exists on a different thread
    def stop(self):
        self.__ueconnect.stopEvent.set()
        time.sleep(1)
                
    #startes the connection on current thread blocking it
    def start(self) -> None:
        try:
            asyncio.get_event_loop().run_until_complete(self.__ueconnect.connect())
            self.__connected = True
            #change resolution if pixel streaming output video
            if self.__useV:
                print(f'changing resolution to {self.__res[0]}x{self.__res[1]}')
                pixRes = PixResolution(self.__res[0], self.__res[1])
                self.sendData(pixRes)
                
            #process loop for the connection
            asyncio.get_event_loop().run_until_complete(self.__ueconnect.waitLoop())

        except KeyboardInterrupt:
            print('interrupt')
        finally:
            print('Stopping')
            asyncio.get_event_loop().run_until_complete(self.__ueconnect.closeEverything())
            cv2.destroyAllWindows()
            print('deinitializing subsystems')
            for subsys in self.subModuleList:
                if hasattr(subsys, 'deinitialize'):
                    subsys.deinitialize()
            print('Done!!')

    #starts the connection on a new thread letting the main thread continue
    def start_newThread(self):
        subT = threading.Thread(target=_threadStarter, args=[self], daemon=True)
        subT.start()

    #gets the stats of the peer connection
    def getStats(self) -> dict:
        return asyncio.get_event_loop().run_until_complete(self.__ueconnect.getPeerCStats())

    #sends the data message to unreal with an optional callback function on the response
    def sendData(self, data: UERequestDataInterface, callback: Callable[[dict], None] = None) -> None:
        if self.__connected:
            data.messageID = self.__ccounter
            if callable(callback):
                self.callbackDict[data.messageID] = callback
                data.callback = True

            self.__setupCallback(data)
            self.__ccounter += 1

            dataDict = data.formData()
            jstring = json.dumps(dataDict)

            self.__ueconnect.addDataQ(jstring)

    #keyName corresponds to the JSKeyCode enum
    def sendInputKey(self, keyName: str, isPressed: bool) -> None:
        if self.__connected:
            self.__ueconnect.addInputQ(keyName, isPressed)

    #locations are 0 to 100  float as a percentage of the screen
    def sendMouseButton(self, buttonName: str, isPressed: bool, xLoc: float, yLoc: float) -> None:
        if self.__connected:
            self.__ueconnect.addInputQ((buttonName, xLoc, yLoc), isPressed)

    #deltas are -100 to 100  float as a percentage of the screen
    def sendMouseMove(self, xLoc: float, dx: float, yLoc: float, dy: float) -> None:
        if self.__connected:
            self.__ueconnect.addInputQ(('move', xLoc, yLoc), (dx, dy))