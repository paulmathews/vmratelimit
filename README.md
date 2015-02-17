This is a script intended to be executed via a cron. When executed, the cron
executes and checks if the qvo devices for VMs have changed. If a change has
occured, or if /tmp/qvos does not exist, it will read the config file and
apply ratelimits for all qvos on the system.
