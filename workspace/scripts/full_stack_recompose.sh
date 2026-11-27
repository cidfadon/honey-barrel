#!/bin/bash
##
## (c) 2026 Honey Barrel Labs
##
## Full stack stop and re-compose script for the Honey Barrel project.
## Script is designed to stop all running containers, optionally remove 
## them, and then re-compose the full stack using Docker Compose.
## Script provides options to build without cache, recreate containers, 
## start in detached mode.
##
## CAREFUL: Uncomment required sections if you need to remove volumes or orphan containers.
##

WORKSPACE_DIR="/home/me/git-repo/honey-barrel/workspace"
cd "$WORKSPACE_DIR" || { echo "Failed to change directory to $WORKSPACE_DIR"; exit 1; }

MODE="services"
SERVICES=()

show_help() {
	echo "Usage: $(basename "$0") [SERVICE_NAME ... | all | --help]"
	echo ""
	echo "Examples:"
	echo "  $(basename "$0") investment-analyst-api"
	echo "  $(basename "$0") investment-analyst-api hermes mcp-gateway"
	echo "  $(basename "$0") all"
}

if [[ "$1" == "--help" || "$1" == "-h" ]]; then
	show_help
	exit 0
fi

if [[ $# -eq 0 ]]; then
	MODE="all"
elif [[ "$1" == "all" ]]; then
	if [[ $# -gt 1 ]]; then
		echo "Option 'all' cannot be mixed with service names."
		exit 1
	fi
	MODE="all"
else
	SERVICES=("$@")
fi

if [[ "$MODE" == "services" ]]; then
	AVAILABLE_SERVICES="$(docker compose config --services)"
	for SERVICE in "${SERVICES[@]}"; do
		if ! grep -Fxq "$SERVICE" <<< "$AVAILABLE_SERVICES"; then
			echo "Service '$SERVICE' not found in docker-compose.yml"
			echo "Available services:"
			echo "$AVAILABLE_SERVICES"
			exit 1
		fi
	done
fi

## ----------------- Compose DOWN ------------------
##  Remove all containers, networks, and volumes defined in the docker-compose.yml file.
#docker compose down -v --remove-orphans

##  Remove only --remove-orphans
#docker compose down --remove-orphans

##  Remove all stopped containers, unused networks, and dangling images and build cache.
##  This command will not remove volumes, so any data stored in volumes will be preserved.
if [[ "$MODE" == "all" ]]; then

	#docker compose down 
    docker compose down --remove-orphans

else
	docker compose stop "${SERVICES[@]}"
	docker compose rm -f "${SERVICES[@]}"
fi

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
				if [[ "$MODE" == "all" ]]; then
					docker compose build --no-cache
				else
					docker compose build --no-cache "${SERVICES[@]}"
				fi
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
				if [[ "$MODE" == "all" ]]; then
					docker compose up -d --no-deps --force-recreate
				else
					docker compose up -d --no-deps --force-recreate "${SERVICES[@]}"
				fi
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
				if [[ "$MODE" == "all" ]]; then
					docker compose up -d
				else
					docker compose up -d "${SERVICES[@]}"
				fi
				exit 0
                break;;
			[Nn]* )
				echo -e "\nContinue without \"detached\" option.."
				if [[ "$MODE" == "all" ]]; then
					docker compose up
				else
					docker compose up "${SERVICES[@]}"
				fi
                exit 0
				break ;;
			* ) echo "Please answer yes or no..";;
		esac
	done

echo -e "\nFull stack containers re-composed and UP.."
exit 0




