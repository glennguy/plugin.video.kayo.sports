import arrow

from matthuisman import plugin, gui, settings, userdata, signals, inputstream
from matthuisman.exceptions import PluginError

from .api import API
from .language import _
from .constants import HEADERS, SERVICE_TIME, LIVE_PLAY_TYPE, FROM_LIVE

api = API()

@signals.on(signals.BEFORE_DISPATCH)
def before_dispatch():
    api.new_session()
    plugin.logged_in = api.logged_in

@plugin.route('')
def home():
    folder = plugin.Folder(cacheToDisc=False)

    if not api.logged_in:
        folder.add_item(label=_(_.LOGIN, _bold=True), path=plugin.url_for(login))
    else:
        folder.add_item(label=_(_.SHOWS, _bold=True), path=plugin.url_for(shows))
        folder.add_item(label=_(_.SPORTS, _bold=True), path=plugin.url_for(sports))

        folder.add_items(_landing('home'))

        #folder.add_item(label=_.SELECT_PROFILE, path=plugin.url_for(select_profile))
        folder.add_item(label=_.LOGOUT, path=plugin.url_for(logout))

    folder.add_item(label=_.SETTINGS, path=plugin.url_for(plugin.ROUTE_SETTINGS))

    return folder

@plugin.route()
def login():
    username = gui.input(_.ASK_USERNAME, default=userdata.get('username', '')).strip()
    if not username:
        return

    userdata.set('username', username)

    password = gui.input(_.ASK_PASSWORD).strip()
    if not password:
        return

    api.login(username=username, password=password)

    #_select_profile()

    gui.refresh()

# @plugin.route()
# def select_profile():
#     _select_profile()
#     gui.refresh()

@plugin.route()
def logout():
    if not gui.yes_no(_.LOGOUT_YES_NO):
        return

    api.logout()
    gui.refresh()

@plugin.route()
def shows():
    folder = plugin.Folder(title=_.SHOWS)
    folder.add_items(_landing('shows'))
    return folder 

@plugin.route()
def sports():
    folder = plugin.Folder(title=_.SPORTS)
   # folder.add_items(_sport('default'))
    folder.add_items(_landing('sports'))
    return folder

# @plugin.route()
# def sport(sport, name):
#     folder = plugin.Folder(title=name)
#     folder.add_items(_sport(sport))
#     folder.add_items(_landing('sport', sport=sport))
#     return folder

@plugin.route()
def show(id, title):
    data = api.show(id)

    folder = plugin.Folder(title=title)
    for row in data:
        if row['title'] == 'Episodes':
            folder.add_items(_parse_contents(row.get('contents', [])))

    return folder

@plugin.route()
def panel(id):
    data = api.panel(id)
    folder = plugin.Folder(title=data['title'])
    folder.add_items(_parse_contents(data.get('contents', [])))
    return folder

@plugin.route()
def alert(asset, title, image):
    alerts = userdata.get('alerts', [])

    if asset not in alerts:
        alerts.append(asset)
        gui.notification(_.REMINDER_SET, heading=title, icon=image)
    else:
        alerts.remove(asset)
        gui.notification(_.REMINDER_REMOVED, heading=title, icon=image)

    userdata.set('alerts', alerts)
    gui.refresh()

@plugin.route()  
def playlist(output=''):
    playlist = '#EXTM3U x-tvg-url=""\n\n'

    count = 1
    data = api.panel('yJbvNNbmxlD6')
    for row in data.get('contents', []):
        asset = row['data']['asset']

        if row['contentType'] != 'video':
            continue

        playlist += '#EXTINF:-1 tvg-name="{count:03d}" tvg-id="{id}" tvg-logo="{logo}",{name}\n{path}\n\n'.format(
            count=count, id=asset['id'], logo=_get_image(asset, 'carousel-item'), name=asset['title'], path=plugin.url_for(play, id=asset['id']))
        count += 1

    playlist = playlist.strip()

    output = output or 'playlist.m3u8'
    with open(output, 'w') as f:
        f.write(playlist)


@plugin.route()
@plugin.login_required()
def play(id, start_from=0):
    asset = api.stream(id)

    start = arrow.get(asset.get('preCheckTime', asset['transmissionTime']))

    if start > arrow.now():
        return gui.ok(_(_.GAME_NOT_STARTED, start=start.humanize()))

    stream = _get_stream(asset)

    item = plugin.Item(
        path = stream['manifest']['uri'],
        art = False,
        headers = HEADERS,
    )

    if stream['mediaFormat'] == 'dash':
        item.inputstream = inputstream.MPD()
    elif stream['mediaFormat'] == 'hls-ts':
        item.inputstream = inputstream.HLS()

    if start_from:
        item.properties['ResumeTime'] = start_from
        item.properties['TotalTime']  = start_from

    return item

@signals.on(signals.ON_SERVICE)
def service():
    alerts = userdata.get('alerts', [])
    if not alerts:
        return

    now = arrow.now()

    _alerts = []
    for id in alerts:
        asset = api.event(id)
        start = arrow.get(asset.get('preCheckTime', asset['transmissionTime']))

        if asset.get('isStreaming', False):
            if gui.yes_no(_(_.EVENT_STARTED, event=asset['title']), yeslabel=_.WATCH, nolabel=_.CLOSE):
                play(id).play()
        elif start > now or (now - start).seconds < SERVICE_TIME:
            _alerts.append(id)

    userdata.set('alerts', _alerts)

def _get_stream(asset):
    streams = [asset['recommendedStream']]
    streams.extend(asset['alternativeStreams'])

    playable = ['hls-ts', 'dash']
    streams  = [s for s in streams if s['mediaFormat'] in playable]
    streams  = sorted(streams, key=lambda k: (k['mediaFormat'] == 'hls-ts', k['provider'] == 'AKAMAI'), reverse=True)

    if not streams:
        raise PluginError(_.NO_STREAM)

    return streams[0]

# def _select_profile():
#     profiles = api.profiles()
#     profiles.append({'id': None, 'name': _.NO_PROFILE})

#     index = gui.select(_.SELECT_PROFILE, options=[p['name'] for p in profiles])
#     if index < 0:
#         return

#     userdata.set('profile', profiles[index]['id'])

def _sport(sport):
    items = []

    #https://vccapi.kayosports.com.au/content/types/landing/names/sport?sport=tennis&evaluate=3&profile=d3bf57f6ce9bbadf05488e7fd82972e899e857be

    for row in api.sport_menu(sport):
        item = plugin.Item(
            label = row['name'],
            path = plugin.url_for(sport_list, sport=row['sport'], name=row['name']),
            art = {'thumb': 'https://resources.kayosports.com.au/production/sport-logos/1x1/{}.png?imwidth=320'.format(row['sport'])},
        )
        items.append(item)

    return items

def _landing(name):
    items = []

    for row in api.landing(name):
        if row['panelType'] == 'hero-carousel' and 'contents' in row:
            items.extend(_parse_contents(row['contents']))
        else:
            items.append(_parse_panel(row))

    return items

def _parse_panel(row):
    #art = {}
    # items = _parse_contents(row.get('contents', []))
    # if items:
    #     art = items[0].art

    return plugin.Item(
        label = row['title'],
        path  = plugin.url_for(panel, id=row['id']),
    #    art   = art,
    )

def _parse_contents(rows):
    items = []

    for row in rows:
        asset = row['data']['asset']

        if row['contentType'] == 'video':
            items.append(_parse_video(asset))
        elif row['contentType'] == 'section':
            items.append(_parse_show(asset))

    return items

def _parse_video(asset):
    alerts = userdata.get('alerts', [])
    
    now   = arrow.now()
    start = arrow.get(asset['transmissionTime'])
    precheck = start

    if 'preCheckTime' in asset:
        precheck = arrow.get(asset['preCheckTime'])
        if precheck > start:
            precheck = start

    start_from = (start - precheck).seconds
    
    item = plugin.Item(
        label = asset['title'],
        art  = {
            'thumb': _get_image(asset, 'carousel-item'),
            'fanart': _get_image(asset, 'hero-default'),
        },
        info = {
            'plot': asset.get('description'),
            'plotoutline': asset.get('description-short'),
            'mediatype': 'video',
        },
        playable = True,
        is_folder = False,
    )

    is_live = False

    if now < start:
        is_live = True
        item.label = _(_.STARTING_SOON, title=asset['title'], humanize=start.humanize())
        toggle_alert = plugin.url_for(alert, asset=asset['id'], title=asset['title'], image=item.art['thumb'])

        if asset['id'] not in userdata.get('alerts', []):
            item.info['playcount'] = 0
            item.context.append((_.SET_REMINDER, "XBMC.RunPlugin({})".format(toggle_alert)))
        else:
            item.info['playcount'] = 1
            item.context.append((_.REMOVE_REMINDER, "XBMC.RunPlugin({})".format(toggle_alert)))

    elif asset['isLive'] and asset.get('isStreaming', False):
        is_live = True
        item.label = _(_.LIVE, title=asset['title'])

        item.context.append((_.FROM_LIVE, "XBMC.PlayMedia({})".format(
            plugin.url_for(play, id=asset['id'], is_live=is_live, start_from=0)
        )))

        item.context.append((_.FROM_START, "XBMC.PlayMedia({})".format(
            plugin.url_for(play, id=asset['id'], is_live=is_live, start_from=start_from)
        )))

    index = settings.getInt('live_play_type', 0)
    if is_live and LIVE_PLAY_TYPE[index] == FROM_LIVE:
        start_from = 0

    item.path = plugin.url_for(play, id=asset['id'], is_live=is_live, start_from=start_from)

    return item

def _parse_show(asset):
    return plugin.Item(
        label = asset['title'],
        art  = {
            'thumb': _get_image(asset, 'carousel-item'),
            'fanart': _get_image(asset, 'hero-default'),
        },
        info = {
            'plot': asset.get('description-short'),
            'mediatype': 'tvshow',
        },
        path = plugin.url_for(show, id=asset['id'], title=asset['title']),
    )

def _get_image(asset, type='carousel-item', width=2048):
    if 'image-pack' not in asset:
        return None

    return 'https://vmndims.kayosports.com.au/api/v2/img/{}?location={}&imwidth={}'.format(asset['image-pack'], type, width)