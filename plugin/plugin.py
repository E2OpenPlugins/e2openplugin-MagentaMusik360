# -*- coding: utf-8 -*-
from __future__ import print_function

from skin import loadSkin
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.InfoBarGenerics import InfoBarMenu, InfoBarSeek, InfoBarNotifications, InfoBarServiceNotifications, InfoBarShowHide, InfoBarSimpleEventView, InfoBarServiceErrorPopupSupport
from Screens.MessageBox import MessageBox
from Screens.Standby import TryQuitMainloop
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Screens.Setup import SetupSummary
from Components.ActionMap import ActionMap
from Components.ServiceEventTracker import InfoBarBase
from Components.Sources.List import List
from Components.Label import Label
from Components.MultiContent import MultiContentEntryText, MultiContentEntryProgress
from Components.ConfigList import ConfigListScreen
from Components.config import config, getConfigListEntry, ConfigSubsection, ConfigText, ConfigPassword, ConfigInteger, ConfigNothing, ConfigYesNo, ConfigSelection, NoSave
from Tools.BoundFunction import boundFunction
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from downloader import MagentMusik360DownloadWithProgress

from enigma import eTimer, eListboxPythonMultiContent, gFont, eEnv, eServiceReference, getDesktop, eConsoleAppContainer

import xml.etree.ElementTree as ET
import time
import urllib
import urllib2
import json
import base64
import re
from itertools import cycle, izip
from datetime import datetime
from twisted.web.client import Agent, readBody
from twisted.internet import reactor
from twisted.web.http_headers import Headers


if getDesktop(0).size().width() <= 1280:
	loadSkin(resolveFilename(SCOPE_PLUGINS) + "Extensions/MagentaMusik360/skin_hd.xml")
else:
	loadSkin(resolveFilename(SCOPE_PLUGINS) + "Extensions/MagentaMusik360/skin_fhd.xml")

try:
	from enigma import eMediaDatabase
	magentamusik_isDreamOS = True

	import ssl
	try:
		_create_unverified_https_context = ssl._create_unverified_context
	except AttributeError:
		pass
	else:
		ssl._create_default_https_context = _create_unverified_https_context

except:
	magentamusik_isDreamOS = False

#==== workaround for TLSv1_2 with DreamOS =======
from OpenSSL import SSL
from twisted.internet.ssl import ClientContextFactory
try:
	# available since twisted 14.0
	from twisted.internet._sslverify import ClientTLSOptions
except ImportError:
	ClientTLSOptions = None
#================================================

config.plugins.magentamusik360 = ConfigSubsection()
# Some images like DreamOS need streams with fix quality
config.plugins.magentamusik360.fix_stream_quality = ConfigYesNo(default = magentamusik_isDreamOS)
config.plugins.magentamusik360.stream_quality = ConfigSelection(default = "2", choices = [("0", _("sehr gering")), ("1", _("gering")), ("2", _("mittel")), ("3", _("hoch")), ("4", _("sehr hoch"))])


def loadMagentaMusikJsonData(screen, statusField, buildListFunc, data):
	try:
		jsonResult = json.loads(data)

		buildListFunc(jsonResult)
	except Exception as e:
		statusField.setText(screen + ': Fehler beim Laden der JSON Daten "' + str(e) + '"')

def handleMagentaMusikWebsiteResponse(callback, response):
	d = readBody(response)
	d.addCallback(callback)
	return d

def handleMagentaMusikDownloadError(screen, statusField, err):
	statusField.setText(screen + ': Fehler beim Download "' + str(err) + '"')

def downloadMagentaMusikJson(url, callback, errorCallback):
	if magentamusik_isDreamOS == False:
		agent = Agent(reactor)
	else:
		class WebClientContextFactory(ClientContextFactory):
			"A SSL context factory which is more permissive against SSL bugs."

			def __init__(self):
				self.method = SSL.SSLv23_METHOD

			def getContext(self, hostname=None, port=None):
				ctx = ClientContextFactory.getContext(self)
				# Enable all workarounds to SSL bugs as documented by
				# http://www.openssl.org/docs/ssl/SSL_CTX_set_options.html
				ctx.set_options(SSL.OP_ALL)
				if hostname and ClientTLSOptions is not None: # workaround for TLS SNI
					ClientTLSOptions(hostname, ctx)
				return ctx

		contextFactory = WebClientContextFactory()
		agent = Agent(reactor, contextFactory)
	d = agent.request('GET', url, Headers({'user-agent': ['Twisted']}))
	d.addCallback(boundFunction(handleMagentaMusikWebsiteResponse, callback))
	d.addErrback(errorCallback)


class MagentaMusik360MainScreenSummary(SetupSummary):

	def __init__(self, session, parent):
		SetupSummary.__init__(self, session, parent = parent)
		self.skinName = 'SetupSummary'
		self.onShow.append(self.addWatcher)
		self.onHide.append(self.removeWatcher)

	def addWatcher(self):
		self.parent['list'].onSelectionChanged.append(self.selectionChanged)
		self.selectionChanged()

	def removeWatcher(self):
		self.parent['list'].onSelectionChanged.remove(self.selectionChanged)


class MagentaMusik360MoviePlayer(Screen, InfoBarMenu, InfoBarBase, InfoBarSeek, InfoBarNotifications, InfoBarServiceNotifications, InfoBarShowHide, InfoBarSimpleEventView, InfoBarServiceErrorPopupSupport):

	def __init__(self, session, service, standings_url, schedule_url, statistics_url, boxscore_url):
		Screen.__init__(self, session)
		self.skinName = 'MoviePlayer'

		self.title = service.getName()

		InfoBarMenu.__init__(self)
		InfoBarBase.__init__(self)
		InfoBarNotifications.__init__(self)
		InfoBarServiceNotifications.__init__(self)
		InfoBarShowHide.__init__(self)
		InfoBarSimpleEventView.__init__(self)
		InfoBarSeek.__init__(self)
		InfoBarServiceErrorPopupSupport.__init__(self)

		self.service = service
		self.lastservice = self.session.nav.getCurrentlyPlayingServiceReference()
		self.standings_url = standings_url
		self.schedule_url = schedule_url
		self.statistics_url = statistics_url
		self.boxscore_url = boxscore_url

		self['actions'] = ActionMap(['MoviePlayerActions', 'ColorActions', 'OkCancelActions'],
		{
			'leavePlayer' : self.leavePlayer,
			'cancel'      : self.leavePlayer,
			'leavePlayerOnExit' : self.leavePlayerOnExit,
		}, -2)
		self.onFirstExecBegin.append(self.playStream)
		self.onClose.append(self.stopPlayback)

	def playStream(self):
		self.session.nav.playService(self.service)

	def stopPlayback(self):
		if self.lastservice:
			self.session.nav.playService(self.lastservice)
		else:
			self.session.nav.stopService()

	def leavePlayer(self):
		self.session.openWithCallback(self.leavePlayerConfirmed, MessageBox, 'Abspielen beenden?')

	def leavePlayerOnExit(self):
		self.leavePlayer()

	def leavePlayerConfirmed(self, answer):
		if answer:
			self.close()

	def showMovies(self):
		pass

	# for summary
	def createSummary(self):
		from Screens.SimpleSummary import SimpleSummary
		return SimpleSummary


class MagentaMusik360EventScreen(Screen):

	def __init__(self, session, series_title, url, event_type):
		Screen.__init__(self, session)
		self.session = session

		self.setup_title = MagentaMusik360MainScreen.title

		self['concert'] = Label('')
		self['series'] = Label(series_title)
		self['subdescription'] = Label('')
		self['fulldescription'] = Label('')
		self['status'] = Label('Lade Daten...')
		self['version'] = Label(MagentaMusik360MainScreen.version)

		self.videoList = []
		self['list'] = List(self.videoList)

		self['actions'] = ActionMap(['MenuActions', 'SetupActions', 'DirectionActions'],
		{
			'menu': self.closeRecursive,
			'cancel': self.close,
			'ok': self.ok,
		})
		if event_type == 'series':
			downloadMagentaMusikJson(url, boundFunction(loadMagentaMusikJsonData, 'Event', self['status'], self.readSeries), boundFunction(handleMagentaMusikDownloadError, 'Event', self['status']))
		else:
			downloadMagentaMusikJson(url, boundFunction(loadMagentaMusikJsonData, 'Event', self['status'], self.buildScreen), boundFunction(handleMagentaMusikDownloadError, 'Event', self['status']))

	def closeRecursive(self):
		self.close(True)

	def getStreamUrl(self, url):
		try:
			response = urllib2.urlopen(url).read()
			namespace = { 'ns0': 'http://www.w3.org/ns/SMIL' }
			xmlroot = ET.ElementTree(ET.fromstring(response))
			playlisturl = xmlroot.find('ns0:body/ns0:seq/ns0:media', namespace).get('src')
			return playlisturl, 0
		except urllib2.HTTPError as e:
			return '', e.code
		except urllib2.URLError as e2:
			if 'CERTIFICATE_VERIFY_FAILED' in str(e2.reason):
				return '', -2
			return '', -1

	def readExtXStreamInfLine(self, line, attributeListPattern):
		line = line.replace('#EXT-X-STREAM-INF:', '')
		for param in attributeListPattern.split(line)[1::2]:
			if param.startswith('BANDWIDTH='):
				return param.strip().split('=')[1]
		return ''

	def getFixQualtiyStreamUrl(self, m3u8_url):
		try:
			attributeListPattern = re.compile(r'''((?:[^,"']|"[^"]*"|'[^']*')+)''')
			streams = []
			lines = urllib2.urlopen(m3u8_url).readlines()
			if len(lines) > 0 and lines[0] == '#EXTM3U\r\n':
				i = 1
				count_lines = len(lines)
				while i < len(lines) - 1:
					if lines[i].startswith('#EXT-X-STREAM-INF:'):
						bandwith = self.readExtXStreamInfLine(lines[i], attributeListPattern)
						if bandwith and i + 1 < count_lines:
							streams.append((int(bandwith), lines[i+1].strip()))
					i += 1
				if streams:
					streams.sort(key = lambda x : x[0])
					if len(streams) <> 5:
						print('Warning: %d streams in m3u8. 5 expected' % len(streams))
						if int(config.plugins.magentamusik360.stream_quality.value) < 2:
							return streams[0][1]
						else:
							return streams[len(streams)-1][1]
					return streams[int(config.plugins.magentamusik360.stream_quality.value)][1]
			return ''
		except:
			return ''

	def playVideo(self, title, url):
		playlisturl, errorCode = self.getStreamUrl(url)
		if errorCode == 403:
			self['status'].setText('Es wird ein Abo benötigt um den Inhalt anzuzeigen!')
			self['status'].show()
			return
		elif errorCode == -2:
			self['status'].setText('Bitte stellen sie das Datum ein!')
			self['status'].show()
			return
		elif errorCode == -1:
			self['status'].setText('Es ist ein Fehler aufgetreten. Der Stream kann nicht abgespielt werden!')
			self['status'].show()
			return

		if config.plugins.magentamusik360.fix_stream_quality.value:
			url = self.getFixQualtiyStreamUrl(playlisturl)
			if url:
				if url[0:4] == 'http':
					playlisturl = url
				else: # relative url
					playlisturl = playlisturl[0 : playlisturl.find('/index.m3u8') + 1] + url

		ref = eServiceReference(4097, 0, playlisturl)
		ref.setName(title)

		self.session.open(MagentaMusik360MoviePlayer, ref, '', '', '', '')

	def buildScreen(self, jsonData):
		self.videoList = []

		try:
			if jsonData['$type'] == 'player':
				fulldescription = ''
				origTitle = ''
				title = jsonData['content']['feature']['metadata']['title'].encode('utf8')
				if 'originalTitle' in jsonData['content']['feature']['metadata']:
					origTitle = jsonData['content']['feature']['metadata']['originalTitle'].encode('utf8')
					if origTitle == title:
						origTitle = ''
				if 'fullDescription' in jsonData['content']['feature']['metadata']:
					fulldescription = jsonData['content']['feature']['metadata']['fullDescription'].encode('utf8')
				self['concert'].setText(title)
				self['subdescription'].setText(origTitle)
				self['fulldescription'].setText(fulldescription)
				for videos in jsonData['content']['feature']['representations']:
					if videos['quality'] != 'VR':
						for video in videos['contentPackages']:
							url = video['media']['href'].encode('utf8')
							self.videoList.append(('Starte Stream', url))
		except Exception as e:
			self['status'].setText('Bitte Pluginentwickler informieren:\nMagentaMusik360EventScreen ' + str(e))
			return

		self['list'].setList(self.videoList)
		self['status'].hide()

	def readSeries(self, jsonData):
		try:
			for season in jsonData['content']['series']['seasons']:
				url = season['season']['details']['href'].encode('utf8')
				response = urllib2.urlopen(url).read()
				data = json.loads(response)
				for episode in data['content']['season']['episodes']:
					if episode['movie']['flag']['name'] == 'mmStage':
						url = episode['movie']['features'][0]['player']['href'].encode('utf8')
						downloadMagentaMusikJson(url, boundFunction(loadMagentaMusikJsonData, 'Event', self['status'], self.buildScreen), boundFunction(handleMagentaMusikDownloadError, 'Event', self['status']))
						return
		except Exception as e:
			self['status'].setText('Bitte Pluginentwickler informieren:\nMagentaMusik360EventScreen ' + str(e))
			return

	def ok(self):
		if self['list'].getCurrent():
			title = self['list'].getCurrent()[0]
			url = self['list'].getCurrent()[1]
			self.playVideo(title, url)

	# for summary
	def getCurrentEntry(self):
		if self['list'].getCurrent():
			return self['list'].getCurrent()[0]
		return self['concert'].getText()

	def getCurrentValue(self):
		return ' '

	def createSummary(self):
		return MagentaMusik360MainScreenSummary


class MagentaMusik360SectionScreen(Screen):

	def __init__(self, session, title, url):
		Screen.__init__(self, session)
		self.session = session
		self.main_title = title
		self.url = url

		self.setup_title = MagentaMusik360MainScreen.title

		self['title'] = Label(title)
		self['subtitle'] = Label('')
		self['status'] = Label('Lade Daten...')
		self['version'] = Label(MagentaMusik360MainScreen.version)

		self.sectionList = []
		self['list'] = List(self.sectionList)

		self['actions'] = ActionMap(['MenuActions', 'SetupActions', 'DirectionActions', 'ColorActions'],
		{
			'menu': self.closeRecursive,
			'cancel': self.close,
			'ok': self.ok,
		})
		downloadMagentaMusikJson(url, boundFunction(loadMagentaMusikJsonData, 'Section', self['status'], self.buildList), boundFunction(handleMagentaMusikDownloadError, 'Section', self['status']))

	def closeRecursive(self):
		self.close(True)

	def buildList(self, jsonData):
		try:
			title = ''
			if jsonData['$type'] == 'seriesdetails':
				title = jsonData['content']['series']['episodeFeatures']['featureType'].encode('utf8')
				self.sectionList.append((title, '', '', 'series', self.url))
			elif jsonData['$type'] == 'topten':
				for movies in jsonData['content']['teasers']:
					seriesTitle = ''
					origTitle = ''
					title = movies['movie']['title'].encode('utf8')
					if 'originalTitle' in movies['movie']:
						origTitle = movies['movie']['originalTitle'].encode('utf8')
						if origTitle == title:
							origTitle = ''
					url = movies['movie']['player']['href'].encode('utf8')
					if 'seriesTitle' in movies['movie']:
						seriesTitle = movies['movie']['seriesTitle'].encode('utf8')
					self.sectionList.append((title, origTitle, seriesTitle, 'teaser', url))
		except Exception as e:
			self['status'].setText('Bitte Pluginentwickler informieren:\nMagentaMusik360SectionScreen ' + str(e))
			return

		self['list'].setList(self.sectionList)
		self['status'].hide()

	def ok(self):
		if self['list'].getCurrent():
			seriesTitle = self['list'].getCurrent()[2]
			event_type = self['list'].getCurrent()[3]
			url = self['list'].getCurrent()[4]
			if url != '':
				self.session.openWithCallback(self.recursiveClose, MagentaMusik360EventScreen, seriesTitle, url, event_type)

	def recursiveClose(self, *retVal):
		if retVal:
			self.close(True)

	# for summary
	def getCurrentEntry(self):
		return self['title'].getText()

	def getCurrentValue(self):
		if self['list'].getCurrent():
			return self['list'].getCurrent()[0]
		else:
			return ' '

	def createSummary(self):
		return MagentaMusik360MainScreenSummary


class MagentaMusik360MainScreen(Screen):

	version = 'v1.0.1'

	base_url = 'https://wcss.t-online.de/cvss/magentamusic/vodplayer/v3/structuredgrid/58948?$whiteLabelId=MM2'
	title = 'MagentaMusik 360'

	def __init__(self, session, args = None):
		Screen.__init__(self, session)
		self.session = session

		self.updateUrl = ''
		self.updateText = ''
		self.filename = ''

		self.setup_title = MagentaMusik360MainScreen.title

		self['title'] = Label('')
		self['subtitle'] = Label('')
		self['status'] = Label('Lade Daten...')
		self['version'] = Label(self.version)

		self.contentlist = []
		self['list'] = List(self.contentlist)

		self['buttongreen'] = Label('Update')
		self['buttongreen'].hide()

		self['actions'] = ActionMap(['SetupActions', 'DirectionActions', 'ColorActions'],
		{
			'cancel': self.close,
			'ok': self.ok,
			'green': self.update,
		})
		downloadMagentaMusikJson(self.base_url, boundFunction(loadMagentaMusikJsonData, 'Main', self['status'], self.buildList), boundFunction(handleMagentaMusikDownloadError, 'Main', self['status']))
		self.onLayoutFinish.append(self.checkForUpdate)

	def buildList(self, jsonData):
		try:
			if jsonData['$type'] == 'structuredGrid':
				self['title'].setText(jsonData['content']['header']['title'].encode('utf8'))
				for group in jsonData['content']['groups']:
					if group['groupType'] == 'smallTeaser':
						if len(group['items']) == 1:
							title = group['items'][0]['teaser']['header'].encode('utf8')
							self.contentlist.append((title, group['items'][0]['teaser']['target']['href'].encode('utf8')))
					elif group['groupType'] == 'assetList':
						title = group['title'].encode('utf8')
						self.contentlist.append((title, group['showAll']['href'].encode('utf8')))
		except Exception as e:
			self['status'].setText('Bitte Pluginentwickler informieren:\nMagentaMusik360MainScreen ' + str(e))
			return

		self['list'].setList(self.contentlist)
		self['status'].hide()

	def ok(self):
		if self['list'].getCurrent():
			title = self['list'].getCurrent()[0]
			urlpart = self['list'].getCurrent()[1]
			self.session.openWithCallback(self.recursiveClose, MagentaMusik360SectionScreen, title, urlpart)

	def recursiveClose(self, *retVal):
		if retVal:
			self.close()

	# for summary
	def getCurrentEntry(self):
		if self['list'].getCurrent():
			return self['list'].getCurrent()[0]
		else:
			return ' '

	def getCurrentValue(self):
		return ' '

	def createSummary(self):
		return MagentaMusik360MainScreenSummary

	# for update
	def checkForUpdate(self):
		url = 'https://api.github.com/repos/E2OpenPlugins/e2openplugin-MagentaMusik360/releases'
		header = { 'Accept' : 'application/vnd.github.v3+json' }
		req = urllib2.Request(url, None, header)
		try:
			response = urllib2.urlopen(req)
			jsonData = json.loads(response.read())

			for rel in jsonData:
				if rel['target_commitish'] != 'master':
					continue
				if self.version < rel['tag_name']:
					self.updateText = rel['body'].encode('utf8')
					for asset in rel['assets']:
						if magentamusik_isDreamOS and asset['name'].endswith('.deb'):
							self.updateUrl = asset['browser_download_url'].encode('utf8')
							self.filename = '/tmp/enigma2-plugin-extensions-magentamusik360.deb'
							self['buttongreen'].show()
							break
						elif (not magentamusik_isDreamOS) and asset['name'].endswith('.ipk'):
							self.updateUrl = asset['browser_download_url'].encode('utf8')
							self.filename = '/tmp/enigma2-plugin-extensions-magentamusik360.ipk'
							self['buttongreen'].show()
							break
				if self.version >= rel['tag_name'] or self.updateUrl != '':
					break
		except Exception as e:
			pass

	def update(self):
		if self.updateUrl:
			self.session.openWithCallback(self.updateConfirmed, MessageBox, 'Ein Update ist verfügbar. Wollen sie es installieren?\nInformationen:\n' + self.updateText, MessageBox.TYPE_YESNO, default = False)

	def updateConfirmed(self, answer):
		if answer:
			self.downloader = MagentMusik360DownloadWithProgress(self.updateUrl, self.filename)
			self.downloader.addError(self.updateFailed)
			self.downloader.addEnd(self.downloadFinished)
			self.downloader.start()

	def downloadFinished(self):
		self.downloader.stop()
		self.container = eConsoleAppContainer()
		if magentamusik_isDreamOS:
			self.container.appClosed_conn = self.container.appClosed.connect(self.updateFinished)
			self.container.execute('dpkg -i ' + self.filename)
		else:
			self.container.appClosed.append(self.updateFinished)
			self.container.execute('opkg update; opkg install ' + self.filename)

	def updateFailed(self, reason, status):
		self.updateFinished(1)

	def updateFinished(self, retval):
		self['buttongreen'].hide()
		self.updateUrl = ''
		if retval == 0:
			self.session.openWithCallback(self.restartE2, MessageBox, 'Das MagentaMusik360 Plugin wurde erfolgreich installiert!\nSoll das E2 GUI neugestartet werden?', MessageBox.TYPE_YESNO, default = False)
		else:
			self.session.open(MessageBox, 'Bei der Installation ist ein Problem aufgetreten.', MessageBox.TYPE_ERROR)

	def restartE2(self, answer):
		if answer:
			self.session.open(TryQuitMainloop, 3)


def main(session, **kwargs):
	session.open(MagentaMusik360MainScreen)

def Plugins(**kwargs):
	return PluginDescriptor(name='MagentaMusik360', description=_('MagentaMusik 360 Plugin'), where = PluginDescriptor.WHERE_PLUGINMENU, icon='plugin.png', fnc=main)
