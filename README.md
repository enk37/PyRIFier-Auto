# PyRIFier-Auto
PyEZ RIPE Filter Automation, hence PyRIFier-Auto. This is simple Python RIPE database parsing tool that finds all routes for AS or AS-SET and updates JunOS prefix list. Can be useful for cron based tasks to update your filters.

usage: pyrifier-auto.py [-h] -t router -l prefix-list [-p port]
                              [-u username] [-k keyfile] [-n as-set] [-d]

  -h, --help      show this help message and exit
  
  -t router       Target router to connect
  
  -l prefix-list  prefix-list name
  
  -p port         NETCONF TCP port, default is 830
  
  -u username     Remote username
  
  -k keyfile      Path to ssh key file, default is ~/.ssh/id_rsa
  
  -n as-set       BGP AS or AS-SET to resolve into corresponding routes
  
  -d              delete prefix list or clear it before updating with new data if combined with -n option
