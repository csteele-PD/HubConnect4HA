/*
 * HubConnect4HA Generic Entity
 *
 * Generic fallback driver for Home Assistant entities that do not map to a
 * native HubConnect device class yet.
 */
def getDriverVersion() {[platform: "Universal", major: 0, minor: 1, build: 0]}

metadata
{
	definition(name: "HubConnect4HA Generic Entity", namespace: "shackrat", author: "HubConnect4HA")
	{
		capability "Temperature Measurement"
		capability "Refresh"
		capability "Sensor"

		attribute "value", "string"
		attribute "rawState", "string"
		attribute "unit", "string"
		attribute "entityId", "string"
		attribute "domain", "string"
		attribute "deviceClass", "string"
		attribute "friendlyName", "string"
		attribute "lastChanged", "string"
		attribute "version", "string"

		command "sync"
	}
}


def installed()
{
	initialize()
}


def updated()
{
	initialize()
}


def initialize()
{
	refresh()
}


def uninstalled()
{
	parent?.sendDeviceEvent(device.deviceNetworkId, "uninstalled")
}


def parse(String description)
{
	log.trace "Msg: Description is $description"
}


def refresh()
{
	parent.sendDeviceEvent(device.deviceNetworkId, "refresh")
}


def sync()
{
	parent.syncDevice(device.deviceNetworkId, "h4hageneric")
	sendEvent([name: "version", value: "v${driverVersion.major}.${driverVersion.minor}.${driverVersion.build}"])
}
