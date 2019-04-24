import arrow

from matthuisman import plugin, gui, settings, userdata, signals, inputstream
from matthuisman.exceptions import PluginError
from matthuisman.session import Session

from .api import API
from .language import _
from .constants import HEADERS, SERVICE_TIME, LIVE_PLAY_TYPES, FROM_LIVE, FROM_START, FROM_CHOOSE, IMG_URL, SPORT_LOGO, CHANNELS_PANEL

api = API()

@signals.on(signals.BEFORE_DISPATCH)
def before_dispatch():
    api.new_session()
    plugin.logged_in = api.logged_in

@plugin.route('')
def home(**kwargs):
    folder = plugin.Folder(cacheToDisc=False)

    if not api.logged_in:
        folder.add_item(label=_(_.LOGIN, _bold=True),  path=plugin.url_for(login))
    else:
        folder.add_item(label=_(_.SHOWS, _bold=True),  path=plugin.url_for(shows))
        folder.add_item(label=_(_.SPORTS, _bold=True), path=plugin.url_for(sports))
        folder.add_items(_landing('home'))

    folder.add_item(label=_.SETTINGS, path=plugin.url_for(plugin.ROUTE_SETTINGS))

    return folder

@plugin.route()
def login(**kwargs):
    username = gui.input(_.ASK_USERNAME, default=userdata.get('username', '')).strip()
    if not username:
        return

    userdata.set('username', username)

    password = gui.input(_.ASK_PASSWORD, hide_input=True).strip()
    if not password:
        return

    api.login(username=username, password=password)
    _select_profile()
    gui.refresh()

@plugin.route()
@plugin.login_required()
def logout(**kwargs):
    if not gui.yes_no(_.LOGOUT_YES_NO):
        return

    api.logout()
    gui.refresh()

@plugin.route()
def shows(**kwargs):
    folder = plugin.Folder(title=_.SHOWS)
    folder.add_items(_landing('shows'))
    return folder 

@plugin.route()
def sports(**kwargs):
    folder = plugin.Folder(title=_.SPORTS)

    for row in api.sport_menu():
        slug = row['url'].split('sport!')[1]

        folder.add_item(
            label = row['name'],
            path  = plugin.url_for(sport, slug=slug, title=row['name']),
            art   = {
                'thumb': SPORT_LOGO.format(row['sport']),
            },
        )

    folder.add_items(_landing('sports'))

    return folder

@plugin.route()
def sport(slug, title, **kwargs):
    folder = plugin.Folder(title=title)
    folder.add_items(_landing('sport', sport=slug))
    return folder

@plugin.route()
def show(id, title, **kwargs):
    data = api.show(id, profile=userdata.get('profile'))

    folder = plugin.Folder(title=title)
    for row in data:
        if row['title'] == 'Episodes':
            folder.add_items(_parse_contents(row.get('contents', [])))

    return folder

@plugin.route()
def panel(id, sport=None, **kwargs):
    data = api.panel(id, sport=sport, profile=userdata.get('profile'))
    folder = plugin.Folder(title=data['title'])
    folder.add_items(_parse_contents(data.get('contents', [])))
    return folder

@plugin.route()
def alert(asset, title, **kwargs):
    alerts = userdata.get('alerts', [])

    if asset not in alerts:
        alerts.append(asset)
        gui.notification(title, heading=_.REMINDER_SET)
    else:
        alerts.remove(asset)
        gui.notification(title, heading=_.REMINDER_REMOVED)

    userdata.set('alerts', alerts)
    gui.refresh()

@plugin.route()  
def playlist(output, **kwargs):
    playlist = '#EXTM3U x-tvg-url=""\n\n'

    data = api.panel(CHANNELS_PANEL)

    for row in data.get('contents', []):
        asset = row['data']['asset']

        if row['contentType'] != 'video':
            continue

        playlist += '#EXTINF:-1 tvg-id="{id}" tvg-logo="{logo}",{name}\n{path}\n\n'.format(
            id=asset['id'], logo=_get_image(asset, 'video', 'thumb'), name=asset['title'], path=plugin.url_for(play, id=asset['id']))

    playlist = playlist.strip()
    with open(output, 'w') as f:
        f.write(playlist)

# @plugin.route()  
# def epg(output, **kwargs):
#     Session().chunked_dl(EPG_URL, output) different ids = won't work

@plugin.route()
@plugin.login_required()
def select_profile(**kwargs):
    _select_profile()
    gui.refresh()

def _select_profile():
    profiles = api.profiles()
    profiles.append({'id': None, 'name': _.NO_PROFILE})

    index = gui.select(_.SELECT_PROFILE, options=[p['name'] for p in profiles])
    if index < 0:
        return

    userdata.set('profile', profiles[index]['id'])

def _get_stream(asset):
    streams = [asset['recommendedStream']]
    streams.extend(asset['alternativeStreams'])

    playable = ['hls-ts', 'dash']
    streams  = [s for s in streams if s['mediaFormat'] in playable]
    streams  = sorted(streams, key=lambda k: (k['mediaFormat'] == 'hls-ts', k['provider'] == 'AKAMAI'), reverse=True)

    if not streams:
        raise PluginError(_.NO_STREAM)

    return streams[0]

def _landing(name, sport=None):
    items = []

    for row in api.landing(name, sport=sport, profile=userdata.get('profile')):
        if row['panelType'] == 'hero-carousel' and row.get('contents') and settings.getBool('show_hero_contents', True):
            items.extend(_parse_contents(row['contents']))

        elif row['panelType'] != 'hero-carousel' and row.get('contents'):
            items.append(plugin.Item(
                label = row['title'],
                path  = plugin.url_for(panel, id=row['id'], sport=sport),
                art   = {
                    'thumb': _get_image(row['contents'][0]['data']['asset'], 'panel', 'thumb'),
                    'fanart': _get_image(row['contents'][0]['data']['asset'], 'panel', 'fanart'),
                },
            ))

    return items

def _parse_contents(rows):
    items = []

    for row in rows:
        asset = row['data']['asset']

        if row['contentType'] == 'video':
            items.append(_parse_video(asset))

        elif row['contentType'] == 'section':
            items.append(_parse_show(asset))

    return items

def _parse_show(asset):
    return plugin.Item(
        label = asset['title'],
        art  = {
            'thumb': _get_image(asset, 'show', 'thumb'),
            'fanart': _get_image(asset, 'show', 'fanart'),
        },
        info = {
            'plot': asset.get('description-short'),
        },
        path = plugin.url_for(show, id=asset['id'], title=asset['title']),
    )

def _get_image(asset, media_type, img_type='thumb', width=None):
    if 'image-pack' not in asset:
        return None

    if img_type == 'thumb':
        return IMG_URL.format(asset['image-pack'], 'carousel-item', width or 415)

    elif img_type == 'fanart':
        return IMG_URL.format(asset['image-pack'], 'hero-default', width or 1920)

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
            'thumb': _get_image(asset, 'video', 'thumb'),
            'fanart': _get_image(asset, 'video', 'fanart'),
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
        toggle_alert = plugin.url_for(alert, asset=asset['id'], title=asset['title'])

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
            plugin.url_for(play, id=asset['id'], is_live=is_live, play_type=FROM_LIVE)
        )))

        item.context.append((_.FROM_START, "XBMC.PlayMedia({})".format(
            plugin.url_for(play, id=asset['id'], is_live=is_live, start_from=start_from, play_type=FROM_START)
        )))

    item.path = plugin.url_for(play, id=asset['id'], is_live=is_live, start_from=start_from, play_type=settings.getEnum('live_play_type', LIVE_PLAY_TYPES, default=FROM_CHOOSE))

    return item

@plugin.route()
@plugin.login_required()
def play(id, start_from=0, play_type=FROM_LIVE, **kwargs):
    asset = api.stream(id)
    start_from = int(start_from)
    play_type  = int(play_type)

    start = arrow.get(asset.get('preCheckTime', asset['transmissionTime']))
    if start > arrow.now():
        raise PluginError(_(_.GAME_NOT_STARTED, start=start.humanize()))

    stream = _get_stream(asset)

    item = plugin.Item(
        path = stream['manifest']['uri'],
        art = False,
        headers = HEADERS,
    )

    if asset['isLive'] and play_type == FROM_LIVE or (play_type == FROM_CHOOSE and gui.yes_no(_.PLAY_FROM, yeslabel=_.FROM_LIVE, nolabel=_.FROM_START)):
        start_from = 0

    hls = inputstream.HLS()

    if stream['mediaFormat'] == 'dash':
        item.inputstream = inputstream.MPD()
    elif stream['mediaFormat'] == 'hls-ts':
        #If live stream FROM_LIVE and no HLS
        if asset['isLive'] and not start_from and not hls.check():
            raise PluginError(_.HLS_REQUIRED)
        else:
            item.inputstream = hls

    if start_from:
        item.properties['ResumeTime'] = start_from
        item.properties['TotalTime']  = start_from

    return item

@signals.on(signals.ON_SERVICE)
def service():
    alerts = userdata.get('alerts', [])
    if not alerts:
        return

    now     = arrow.now()
    notify  = []
    _alerts = []
    
    for id in alerts:
        asset = api.event(id)
        start = arrow.get(asset.get('preCheckTime', asset['transmissionTime']))

        #If we are streaming and started less than 10 minutes ago
        if asset.get('isStreaming', False) and (now - start).total_seconds() <= 60*10:
            notify.append(asset)
        elif start > now:
            _alerts.append(id)

    userdata.set('alerts', _alerts)

    for asset in notify:
        if not gui.yes_no(_(_.EVENT_STARTED, event=asset['title']), yeslabel=_.WATCH, nolabel=_.CLOSE):
            continue

        with signals.throwable():
            start_from = 1
            start      = arrow.get(asset['transmissionTime'])
            
            if start < now and 'preCheckTime' in asset:
                precheck = arrow.get(asset['preCheckTime'])
                if precheck < start:
                    start_from = (start - precheck).seconds

            play(id=asset['id'], start_from=start_from, play_type=settings.getEnum('live_play_type', LIVE_PLAY_TYPES, default=FROM_CHOOSE))