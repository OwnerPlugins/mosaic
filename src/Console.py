import os

from os.path import exists as file_exists
from enigma import eConsoleAppContainer


class ConsoleItem:
    def __init__(self, containers, cmd, callback, extra_args, binary=False):

        self.filenamesaved = cmd.split()[-1]
        print(
            "[ConsoleItem] 1111111111111  self.filenamesaved:",
            self.filenamesaved)
        self.containers = containers
        self.callback = callback
        self.extra_args = self.filenamesaved
        self.extraArgs = extra_args if extra_args else self.filenamesaved  # []
        self.binary = binary
        self.container = eConsoleAppContainer()
        self.appResults = []
        name = cmd
        # print('[ConsoleItem] containers:', containers)
        # print("[ConsoleItem] command:", cmd)
        # print("[ConsoleItem] callback:", callback)
        # print("[ConsoleItem] extra_args:", extra_args)
        # print('[ConsoleItem] binary:', binary)
        # print("[ConsoleItem] self.filenamesaved:", self.filenamesaved)
        if name in containers:
            name = str(cmd) + '@' + hex(id(self))
        self.name = name
        print('[ConsoleItem] if name in containers:=', self.name)
        self.containers[name] = self

        if isinstance(cmd, str):
            cmd = [cmd]
        name = cmd

        if callback:
            self.appResults = []
            try:
                self.container.dataAvail_conn = self.container.dataAvail.connect(
                    self.dataAvailCB)
            except BaseException:
                self.container.dataAvail.append(self.dataAvailCB)
        try:
            self.container.appClosed_conn = self.container.appClosed.connect(
                self.finishedCB)
        except BaseException:
            self.container.appClosed.append(self.finishedCB)

        if len(cmd) > 1:
            print("[Console] Processing command '%s' with arguments %s." %
                  (cmd, str(cmd[1:])))
        else:
            print("[Console] Processing command line '%s'." % cmd)

        retval = self.container.execute(*cmd)
        if retval:
            self.finishedCB(retval)

        if self.callback is None:
            pid = self.container.getPID()
            try:
                # print("[Console] Waiting for command (PID %d) to finish." % pid)
                os.waitpid(pid, 0)
                # print("[Console] Command on PID %d finished." % pid)
            except OSError as err:
                print(
                    "[Console] Error %s: Wait for command on PID %d to terminate failed!  (%s)" %
                    (err.errno, pid, err.strerror))

    def dataAvailCB(self, data):
        self.appResults.append(data)

    def finishedCB(self, retval):
        print("[Console] Command '%s' finished." % self.name)
        data = self.appResults
        try:
            del self.containers[self.name]
            # del self.containers[:]
        except Exception as e:
            print('error del self.containers[self.name]:', e)

        try:
            del self.container.dataAvail[:]
        except Exception as e:
            print('error del self.container.dataAvail[:]:', e)

        try:
            del self.container.appClosed[:]
        except Exception as e:
            print('error del self.container.appClosed[:]:', e)

        print("Tipo di dati:", type(self.appResults))
        # print("Contenuto di appResults:", self.appResults[:10])  # Esamina i
        # primi 10 elementi

        callback = self.callback
        if callback is not None:
            try:
                data = b''.join(self.appResults)
            except Exception as e:
                print("[Error] Failed to join appResults:", e)
                # return

            if file_exists('/var/lib/dpkg/status'):
                data = data if self.binary else data.decode()
                # print("[Debug] Data length after join:", len(data))
                print("[Debug] Data length after join:", len(data))

            else:
                try:
                    with open(self.filenamesaved, "wb") as f:
                        f.write(data)
                        print(
                            "[Debug] Successfully wrote:",
                            self.filenamesaved)
                except Exception as e:
                    print("[Error] Failed to write binary data to file:", e)
            print("[Debug] Successfully wrote:", len(data), self.filenamesaved)
            global xfilename
            xfilename = self.filenamesaved
            callback(data, retval, self.extraArgs)


class Console:
    """
        Console by default will work with strings on callback.
        If binary data required class shoud be initialized with Console(binary=True)
    """

    def __init__(self, binary=False):
        self.appContainers = {}
        self.binary = binary
        print('self.binary console=', self.binary)

    def ePopen(self, cmd, callback=None, extra_args=[]):
        print("[Console] command:", cmd)
        return ConsoleItem(
            self.appContainers,
            cmd,
            callback,
            extra_args,
            self.binary)

    def eBatch(self, cmds, callback, extra_args=[], debug=False):
        self.debug = debug
        cmd = cmds.pop(0)
        self.ePopen(cmd, self.eBatchCB, [cmds, callback, extra_args])

    def eBatchCB(self, data, retval, _extra_args):
        (cmds, callback, extra_args) = _extra_args
        if self.debug:
            print(
                '[eBatch] retval=%s, cmds left=%d, data:\n%s' %
                (retval, len(cmds), data))
        if len(cmds):
            cmd = cmds.pop(0)
            self.ePopen(cmd, self.eBatchCB, [cmds, callback, extra_args])
        else:
            callback(extra_args)

    def kill(self, name):
        if name in self.appContainers:
            print("[Console] killing: ", name)
            self.appContainers[name].container.kill()

    def killAll(self):
        for name, item in self.appContainers.items():
            print("[Console] killing: ", name)
            item.container.kill()
