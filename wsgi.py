import sys
# path = './'
# if path not in sys.path:
#   sys.path.append(path)
from map import server as application

if __name__ == "__main__":
    application.run()