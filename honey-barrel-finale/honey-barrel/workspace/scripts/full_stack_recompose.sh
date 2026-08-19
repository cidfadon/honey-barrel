#!/bin/bash

## 
## Full stack stop and re-compose script for the Honey Barrel project.
## Script is designed to stop all running containers, optionally remove 
## them, and then re-compose the full stack using Docker Compose.
## Script provides options to build without cache, recreate containers, 
## start in detached mode.
##
## Uncomment required sections if you need to remove volumes or orphan containers.
##

## ----------------- Compose DOWN ------------------

##  Remove all containers, networks, and volumes defined in the docker-compose.yml file.
#docker compose down -v --remove-orphans

##  Remove only --remove-orphans
#docker compose down --remove-orphans

##  Remove all stopped containers, unused networks, and dangling images and build cache.
##  This command will not remove volumes, so any data stored in volumes will be preserved.
docker compose down 

##  Remove all stopped containers, unused networks, dangling images, and build cache, as well as all unused volumes.
##  This command will remove all unused volumes, so any data stored in volumes will be lost.
#docker system prune -a --volumes -f

##  Remove all stopped containers, unused networks, dangling images, and build cache.
##  This command will not remove volumes, so any data stored in volumes will be preserved.
#docker system prune

echo -e "\nDocker containers down.."
sleep 3

## ----------------- Compose UP ------------------

## Build and start the containers defined in the docker-compose.yml file, without using the cache.
while true
	do
		read -p "Do you wish to continue using \"build\" (no-cache) option? [Y/N] " BUILD
        case "${BUILD}" in
			[Yy]* )
                echo -e "\nContinue with \"build (no-cache)\" option.."
                docker compose build --no-cache 
				break;;
			[Nn]* )
				echo -e "\nContinue without \"build\" option.."
				break ;;
			* ) echo "Please answer yes or no..";;
		esac
	done

##  Start the containers defined in the docker-compose.yml file in detached mode (running in the background). Recreate containers even if their configuration and image haven't changed.
while true
	do
		read -p "Do you wish to recreate containers even if their configuration haven't changed? [Y/N] " RECREATE

        case "${RECREATE}" in
			[Yy]* )
                echo -e "\nContinue with \"recreate\" option.."
                docker compose up -d --force-recreate
				exit 0
                break;;
			[Nn]* )
				echo -e "\nContinue without \"recreate\" option.."
				break ;;
			* ) echo "Please answer yes or no..";;
		esac
	done

##  Start the containers defined in the docker-compose.yml file in detached mode (running in the background).
while true
	do
		read -p "Do you wish to start the containers in detached mode? [Y/N] " DETACHED

        case "${DETACHED}" in
			[Yy]* )
                echo -e "\nContinue with \"detached\" option.."
                docker compose up -d
				exit 0
                break;;
			[Nn]* )
				echo -e "\nContinue without \"detached\" option.."
                docker compose up
                exit 0
				break ;;
			* ) echo "Please answer yes or no..";;
		esac
	done

echo -e "\nFull stack containers re-composed and UP.."
exit 0



