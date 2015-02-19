#!/usr/bin/python

import ConfigParser
import os
import re
import hashlib

def writeFile(md5):
  f = open('/tmp/qvos', 'w')
  f.write(md5)
  f.close

def applyRule(qvo, baserate, burstrate):
  base_rule = os.popen("/usr/bin/ovs-vsctl set interface " + qvo + " ingress_policing_rate=" + str(baserate))
  burst_rule = os.popen("/usr/bin/ovs-vsctl set interface " + qvo + " ingress_policing_burst=" + str(burstrate))
  out = base_rule.read()
  out = burst_rule.read()


cmd = os.popen("/sbin/ip link show")
output = cmd.read()
qvos = re.findall('qvo\w+-\w+', output)
qvos.sort()
cmd_md5 = hashlib.md5('\n'.join(qvos)).hexdigest()
if os.path.isfile('/tmp/qvos'):
  f = open('/tmp/qvos', 'r')
  file_md5 = f.readline()
  f.close
else:
  file_md5 = cmd_md5
  writeFile(cmd_md5)

if cmd_md5 != file_md5:
  writeFile(cmd_md5)

config = ConfigParser.RawConfigParser()
config.read('/etc/vmratelimit.conf')
custom_rates = config.sections()
if 'uplink' in custom_rates:
  applyRule('int-br-ex', config.getint(uplink, 'baserate'), config.getint(uplink, 'burstrate'))
for custom in custom_rates:
  if custom in qvos:
    applyRule(custom, config.getint(custom, 'baserate'), config.getint(custom, 'burstrate'))
    qvos.remove(custom)
for qvo in qvos:
  applyRule(qvo, config.getint('default', 'baserate'), config.getint('default', 'burstrate'))

