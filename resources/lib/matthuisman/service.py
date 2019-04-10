import time
import xbmc
import random

from .router import url_for
from .constants import ROUTE_SERVICE, ROUTE_SERVICE_INTERVAL

def run(interval=ROUTE_SERVICE_INTERVAL):
    url = url_for(ROUTE_SERVICE)
    cmd = 'XBMC.RunPlugin({0})'.format(url)
    last_run = 0

    monitor = xbmc.Monitor()

    #Random start-up wait
    monitor.waitForAbort(random.randint(5, 30))

    while not monitor.waitForAbort(10):
        if time.time() - last_run >= interval:
            xbmc.executebuiltin(cmd)
            last_run = time.time()