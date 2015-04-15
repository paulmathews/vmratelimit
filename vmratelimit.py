#!/usr/bin/python

import ConfigParser
import os
import subprocess
import re
import hashlib
import sys

def writeFile(md5):
  # /tmp/qvos contains the md5sum of the array of qvos from the previous run
  try:
    f = open('/tmp/qvos', 'w')
    f.write(md5)
    f.close
  except:
    sys.stderr.write("Unable to open /tmp/qvos for writing\n")

def applyRule(qvo, baserate, burstrate):
  basecmd = ['/usr/bin/ovs-vsctl', 'set', 'interface', qvo,
         'ingress_policing_rate={0}'.format(baserate)]
  burstcmd = ['/usr/bin/ovs-vsctl', 'set', 'interface', qvo,
         'ingress_policing_burst={0}'.format(burstrate)]
  try:
    subprocess.call(basecmd)
  except:
    raise Exception("Failed to set base rate on %s" % qvo)
  try:
    subprocess.call(burstcmd)
  except:
    raise Exception("Failed to set burst rate on %s" % qvo)

def getUplink():
  config = ConfigParser.RawConfigParser()
  config.read('/etc/neutron/plugin.ini')
  custom_rates = config.sections()
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
    except:
      raise Exception("Unable to find bridge mapping")
  int_dev = "int-" + dev
  return int_dev


p = subprocess.Popen(['/sbin/ip', 'link', 'show'], stdout=subprocess.PIPE)
output = p.communicate()[0]
qvos = re.findall('qvo\w+-\w+', output)
# Sort and md5 the array of current qvos, so we can easily determine if we
# have lost or added new interfaces on the next run
qvos.sort()
cmd_md5 = hashlib.md5('\n'.join(qvos)).hexdigest()
# If we have a file, open it, otherwise, write out the md5
if os.path.isfile('/tmp/qvos'):
  try:
    f = open('/tmp/qvos', 'r')
    file_md5 = f.readline()
    f.close
  except:
    file_md5 = cmd_md5
    writeFile(cmd_md5)
else:
  file_md5 = cmd_md5
  writeFile(cmd_md5)

# If the prior md5 and this run's md5 don't match, write out the current one
if cmd_md5 != file_md5:
  writeFile(cmd_md5)

config = ConfigParser.RawConfigParser()
config.read('/etc/vmratelimit.conf')
custom_rates = config.sections()
# Look for an [uplink] section in the config file, and apply rate
if 'uplink' in custom_rates:
  int_dev = getUplink()
  applyRule(int_dev, config.getint('uplink', 'baserate'),
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
