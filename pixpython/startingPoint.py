from PixControl.subsystemInterface import *
import PixControl.unrealConnect as uc
import cv2
import numpy as np
import datetime
from collections import deque
import threading
import os


# subsystem that displays the video frames
class Vdisplay(SubsystemInterface):
    def initialize(self, client):
        super().initialize(client)

    def onVideo(self, frame):
        cv2.imshow('Camera View', frame[0])
        cv2.waitKey(1)

    def onAudio(self, frame):
        pass

    def onData(self, data):
        print(data)

    def deinitialize(self):
        cv2.destroyAllWindows()


class VRecorder(SubsystemInterface):
    def __init__(self):
        self.folder = f'cap-{datetime.datetime.now()}/'
        self.folder = (self.folder.replace(':', '-')).replace(' ', '_')
        self.path = self.folder

    def initialize(self, client):
        super().initialize(client)
        self.saveQ = deque()
        self.saverT = threading.Thread(target=self.savingLoop, daemon=True)
        os.mkdir(self.path)
        self.stopFlag = threading.Event()
        self.saverT.start()

    def setDir(self, directory):
        self.path = os.path.join(directory, self.folder)

    def savingLoop(self):
        # save things in the deque while things are running
        while True:
            if self.stopFlag.is_set():
                break
            try:
                dt = self.saveQ.popleft()
                img = dt[0]
                cv2.imwrite(f'{self.path}frame_{dt[1]}.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            except IndexError:
                pass
        # save the remaining items when things are shutting down
        try:
            while True:
                dt = self.saveQ.popleft()
                img = dt[0]
                cv2.imwrite(f'{self.path}frame_{dt[1]}.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
        except:
            pass

    def onVideo(self, frame):
        self.saveQ.append(frame)

    def onAudio(self, frame):
        pass

    def onData(self, data):
        pass

    def deinitialize(self):
        self.stopFlag.set()
        print('waiting for saver to join')
        self.saverT.join()


# subsystem that gives the controlled drone for predator prey move commands, needs id hard coded
class PlayerMover(SubsystemInterface):
    def initialize(self, client):
        super().initialize(client)

    def initialize(self, client):
        super().initialize(client)
        self.counter = 0
        self.rng = np.random.default_rng(12345)
        self.x = 0.0
        self.y = 0.0

    def onVideo(self, frame):
        pass

    def onAudio(self, frame):
        pass

    def onData(self, data):
        self.counter += 1
        if self.counter % 101 == 0:
            x = (self.rng.random() - 0.5) * 2000
            y = (self.rng.random() - 0.5) * 2000
            z = (self.rng.random()) * 1000
            move = CallFunction(True, 14864, 'MoveDrone', str(x), str(y), str(z))
            self.ueClient.sendData(move)
            print('move sent')


class PyButtons(SubsystemInterface):
    def __init__(self):
        super().__init__()
        self.w = False
        self.a = False
        self.s = False
        self.d = False
        self.selfID = 0
        self.targetID = 0

    def initialize(self, client):
        super().initialize(client)

    def onVideo(self, frame) -> None:
        pass

    def onAudio(self, frame) -> None:
        pass

    def callbackID(self, data: LocalIDData):
        if isinstance(data, LocalIDData):
            self.selfID = data.agentID

    def onData(self, data: dict) -> None:
        if isinstance(data, WorldData):
            self.counter += 1
            if self.counter == self.interval:
                self.counter = 0
                # get id of controlled agent
                if self.selfID == 0:
                    getID = LocalID()
                    self.ueClient.sendData(getID, self.callbackID)
                else:
                    # going to assume that the target exists and is the same as the predator prey scenario
                    if self.targetID == 0:
                        for id in data.getAllAgentID():
                            if 'ThirdPerson' in data.getAgentNameByID(id):
                                self.targetID = id
                                break

                    # do the calculation to get the point behind the target
                    velocity = np.array(data.getAgentVelocityByID(self.targetID))
                    location = np.array(data.getAgentLocationByID(self.targetID))
                    vnorm = np.linalg.norm(velocity)

                    # if target is not moving, go directly towards target
                    if vnorm == 0:
                        temploc = np.array(data.getAgentLocationByID(self.selfID))
                        velocity = location - temploc
                        vnorm = np.linalg.norm(velocity)
                        if vnorm == 0:
                            return

                    offset = velocity / vnorm
                    offset = offset * 200
                    goal = location + offset

                    # 2d keyboard presses to move the player
                    if goal[0] > self.selfdata.xLocation:
                        if self.w == False:
                            self.ueClient.sendInputKey('w', True)
                            self.w = True
                        if self.s == True:
                            self.ueClient.sendInputKey('s', False)
                            self.s = False
                    elif goal[0] < self.selfdata.xLocation:
                        if self.w == True:
                            self.ueClient.sendInputKey('w', False)
                            self.w = False
                        if self.s == False:
                            self.ueClient.sendInputKey('s', True)
                            self.s = True
                    else:
                        if self.w == True:
                            self.ueClient.sendInputKey('w', False)
                            self.w = False
                        if self.s == True:
                            self.ueClient.sendInputKey('s', False)
                            self.s = False

                    if goal[1] > self.selfdata.yLocation:
                        if self.d == False:
                            self.ueClient.sendInputKey('d', True)
                            self.d = True
                        if self.a == True:
                            self.ueClient.sendInputKey('a', False)
                            self.a = False
                    elif goal[1] < self.selfdata.yLocation:
                        if self.d == True:
                            self.ueClient.sendInputKey('d', False)
                            self.d = False
                        if self.a == False:
                            self.ueClient.sendInputKey('a', True)
                            self.a = True
                    else:
                        if self.a == True:
                            self.ueClient.sendInputKey('a', False)
                            self.a = False
                        if self.d == True:
                            self.ueClient.sendInputKey('d', False)
                            self.d = False


# subsystem that follows the specified target in predator prey scenario
class PlayerFollow(SubsystemInterface):
    def __init__(self):
        super().__init__()
        self.counter = 0
        self.offDist = 200
        self.interval = 30
        self.ttc = 0
        self.selfID = 0
        self.targetID = 0

    def initialize(self, client):
        super().initialize(client)

    def callbackID(self, data: LocalIDData):
        if isinstance(data, LocalIDData):
            self.selfID = data.agentID

    def onVideo(self, frame):
        pass

    def onAudio(self, frame):
        pass

    def onData(self, data):
        if isinstance(data, WorldData):
            self.counter += 1
            if self.counter == self.interval:
                self.counter = 0
                # get id of controlled agent
                if self.selfID == 0:
                    getID = LocalID()
                    self.ueClient.sendData(getID, self.callbackID)
                else:
                    # going to assume that the target exists and is the same as the predator prey scenario
                    if self.targetID == 0:
                        for id in data.getAllAgentID():
                            if 'ThirdPerson' in data.getAgentNameByID(id):
                                self.targetID = id
                                break

                    # do the calculation to get the point behind the target
                    velocity = np.array(data.getAgentVelocityByID(self.targetID))
                    location = np.array(data.getAgentLocationByID(self.targetID))
                    vnorm = np.linalg.norm(velocity)

                    # if target is not moving, go directly towards target
                    if vnorm == 0:
                        temploc = np.array(data.getAgentLocationByID(self.selfID))
                        velocity = location - temploc
                        vnorm = np.linalg.norm(velocity)
                        if vnorm == 0:
                            return

                    offset = velocity / vnorm
                    offset = offset * -self.offDist
                    goal = location + offset
                    # using the move to function on the agent component
                    move = CallFunction(True, self.selfID, 'MoveDrone', str(goal[0]), str(goal[1]), '110')
                    self.ueClient.sendData(move)


def transformParse(data):
    if isinstance(data, TransformData):
        print('Transform data location:', data.location, ' rotation:', data.rotation, ' velocity:', data.velocity)


def raycastParse(data):
    if isinstance(data, TransformData):
        print('Raycast data Hit: ', bool(data.hit), ' location:', data.location, ' actor name:', data.hitActorName)


def worldParse(data):
    if isinstance(data, WorldData):
        wd = data
        print('Is world data type IDs: ', wd.getAllAgentID())
        names = []
        for id in wd.getAllAgentID():
            names.append(wd.getAgentNameByID(id))
        print('names', names)
        print('location:', wd.getAgentLocationByID(14782), ' rotaton:', wd.getAgentRotatioByID(14782))


def localIDcall(data):
    print('Local ID:', data.agentID)


# subsystem that sends out many data requests and parses the responses with callbacks
class tester(SubsystemInterface):
    def initialize(self, client):
        super().initialize(client)
        self.counter = 0

    def onVideo(self, frame):
        self.counter += 1
        if self.counter == 120:
            print('sent requests')
            self.counter = 0
            # tf = Transform(14782)
            # rc = Raycast(14782)
            # cc = ConsoleCommand('stat fps')
            gw = GetWorld()
            li = LocalID()
            # self.ueClient.sendData(tf, transformParse)
            # self.ueClient.sendData(rc, raycastParse)
            # self.ueClient.sendData(cc)
            self.ueClient.sendData(gw, worldParse)
            self.ueClient.sendData(li, localIDcall)

    def onAudio(self, frame):
        pass

    def onData(self, data):
        pass


# starting spot
cc = uc.UEPixClient('localhost', useVideo=True, useAudio=False)
a = Vdisplay()
b = PlayerMover()
c = PlayerFollow()
# d = PyButtons()
e = tester()
f = VRecorder()
cc.addSubModules([a])

cc.start()

##starts the connection in another thread

# import time
# from pprint import pprint
# def begin():
#     cc.start_newThread()
#     counter = 0
#     while cc.isConnected() == False:
#         time.sleep(1)

#     while counter < 10:
#         #print('wait. . .', cc.isConnected())
#         #pprint(cc.getStats())
#         counter += 1
#         time.sleep(1)
#     cc.stop()

# def begin2():
#     cc.start()

# import cProfile
# cProfile.run('begin2()')
