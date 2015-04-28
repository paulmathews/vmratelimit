#!/usr/bin/python

#
# This script uses the ingress policing rates exposed on the veth interface
# by ovs to implement rate limiting. As this is not implemented by neutron,
# and we have no method by which to receive notifications when instances are
# created, this is meant to be run periocially. This script is intended to
# be used as a libvirt post hook, but cron or other execution methods are
# also possible.
#
# To determine if new interfaces have been created since the last run, and
# rates need to be applied, the script enumerates the veth interfaces on the
# system, and creates an md5sum from the list. The md5sum is then saved to disk
# in a temporary file. By reading the md5sum saved, successive executions can
# compare this to the current md5sum and determine if rates need to be applied.
#
# The config file specifies a default rate for instances, but custom rates can
# be applied on a instance by instance basis by specifying the veth interface
# name in the config file.
#

import ConfigParser
import os
import subprocess
import re
import hashlib
import sys

def writeFile(md5):
  # /tmp/qvos contains the md5sum of the array of qvos from the previous run
  try:
    with open('/tmp/qvos', 'w') as f:
      f.write(md5)
  except:
    sys.stderr.write("Unable to open /tmp/qvos for writing\n")

def applyRule(qvo, baserate, burstrate):
  #
  # applyRule takes an interface name, as well as base and burst rates. It does
  # not return a value - simply throwing an exception if ovs-vsctl returns
  # non-zero value.
  #
  basecmd = ['/usr/bin/ovs-vsctl', 'set', 'interface', qvo,
         'ingress_policing_rate={0}'.format(baserate)]
  burstcmd = ['/usr/bin/ovs-vsctl', 'set', 'interface', qvo,
         'ingress_policing_burst={0}'.format(burstrate)]
  try:
    subprocess.call(basecmd, stdout=subprocess.PIPE)
  except:
    raise Exception("Failed to set base rate on %s" % qvo)
  try:
    subprocess.call(burstcmd, stdout=subprocess.PIPE)
  except:
    raise Exception("Failed to set burst rate on %s" % qvo)

def getUplink():
  #
  # getUplink takes no arguments, and returns the bridge device, or
  # throws an exception. It first tries to get the bridge port
  # (default in MOX 6.x), if this fails, it tries to get the veth
  # bridge. If both fail, an exception is raised.
  #
  # MOX 6.x default
  try:
    ovs_port = get_ovs_port()
    try:
      bridge = verify_bridge(ovs_port)
      return bridge
    except:
      pass
  except:
    pass
  # If we don't get a good ovs port, check for veth
  try:
    veth_bridge = get_veth_bridge()
    try:
      bridge = verify_bridge(veth_bridge)
      return bridge
    except:
      raise Exception("Unable to determine uplink")
  except:
    raise Exception("Unable to determine uplink")

def get_veth_bridge():
  #
  # get_veth_bridge takes no arguments, and returns the int veth bridge used by
  # ovs. It parses plugin.ini to determine the bridge_mappings parameter, then
  # prepends 'int-' to get the int bridge.
  #
  config = ConfigParser.RawConfigParser()
  config.read('/etc/neutron/plugin.ini')
  custom_rates = config.sections()
  # bridge_mappings should be in the [ovs] section
  if 'ovs' in custom_rates:
    try:
      value = config.get('ovs', 'bridge_mappings')
      bridgemap = value.split(":")
      # Only the device is present
      if (len(bridgemap) == 1):
        dev = bridgemap[0]
      # physdev:dev syntax
      if (len(bridgemap) == 2):
        dev = bridgemap[1]
      else:
        raise Exception("Unable to find bridge mapping")
      # prepend 'int-' to get the int bridge
      int_dev = "int-" + dev
      return int_dev
    except:
      raise Exception("Unable to find bridge mapping")
  # raise an exception if there is no ovs section
  else:
    raise Exception("Unable to find an [ovs] section in "
                    "/etc/neutron/plugin.ini")

def get_ovs_port():
  #
  # get_ovs_port takes no arguments, and if an integration_bridge is specified
  # in ml2_conf.ini, returns the bridge, or throws an exception
  #
  ml2_conf = ConfigParser.RawConfigParser()
  ml2_conf.read('/etc/neutron/plugins/ml2/ml2_conf.ini')
  try:
    integration_bridge = ml2_conf.get('ovs', 'integration_bridge')
    return integration_bridge
  except:
    raise Exception("No integration_bridge found")

def verify_bridge(bridge):
  #
  # verify_bridge takes a bridge device as an argument. It checks to see if
  # the bridge device is valid, or throws an exception
  #
  cmd = ['/usr/bin/ovs-vsctl', 'list', 'interface', bridge]
  try:
    subprocess.call(cmd, stdout=subprocess.PIPE)
    return bridge
  except:
    raise Exception("Bridge device %s is not valid" % bridge)



if __name__ == "__main__":
  # Get the list of qvos on the system
  p = subprocess.Popen(['/sbin/ip', 'link', 'show'], stdout=subprocess.PIPE)
  output = p.communicate()[0]
  qvos = re.findall('qvo\w+-\w+', output)
  md5 = re.findall('qvo\w+-\w+', output)
  # Sort and md5 the array of current qvos, so we can easily determine if we
  # have lost or added new interfaces on the next run
  qvos.sort()
  with open('/etc/vmratelimit.conf', 'rt') as f:
    # add the config file to the list before hashing to detect config changes
    qvos.append(f.read())
  cmd_md5 = hashlib.md5('\n'.join(qvos)).hexdigest()
  # remove the config element from the list, we use this list later
  file_md5 = []
  qvos.pop()
  # If we have a file, open it, otherwise, write out the md5
  if os.path.isfile('/tmp/qvos'):
    try:
      with open('/tmp/qvos', 'rt') as f:
        file_md5 = f.readline()
    except:
      file_md5 = 0

  # If md5s match, nothing has changed; exit.
  if cmd_md5 == file_md5:
    exit(0)
  # If the prior md5 and this run's md5 don't match, write out the current one
  else:
    writeFile(cmd_md5)

  config = ConfigParser.RawConfigParser()
  config.read('/etc/vmratelimit.conf')
  custom_rates = config.sections()
  # Look for an [uplink] section in the config file, and apply rate
  if 'uplink' in custom_rates:
    # Determine the bridge device
    bridge = getUplink()
    applyRule(bridge, config.getint('uplink', 'baserate'),
    config.getint('uplink', 'burstrate'))
  # Look for specified qvos in the config file, that match current ones - apply
  # the rate, and delete the qvo out of the array
  for custom in custom_rates:
    if custom in qvos:
      applyRule(custom, config.getint(custom, 'baserate'),
              config.getint(custom, 'burstrate'))
      qvos.remove(custom)
  # With all custom-rate qvos eliminated, apply default to remaining qvos
  for qvo in qvos:
    applyRule(qvo, config.getint('default', 'baserate'),
            config.getint('default', 'burstrate'))
