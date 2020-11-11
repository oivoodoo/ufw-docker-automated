#!/usr/bin/env python
import subprocess
import docker

client = docker.from_env()

def manage_ufw():
    docker_ip = None

    networks = client.networks.list(names=['bridge'])
    if len(networks) == 0:
        print("[ufw-docker] missing primary docker gateway ip")
        return
    else:
        docker_ip = networks[0].attrs['IPAM']['Config'][0]['Gateway']

    for event in client.events(decode=True):
        event_type = event.get('status')

        # container network is attached on start or stop event
        if event_type == 'start' or event_type == 'kill':
            container = None
            try:
                container = client.containers.get(event['id'])
            except docker.errors.NotFound as e:
                continue

            container_network = container.attrs['HostConfig']['NetworkMode']
            container_ip = None
            container_port_num = None
            container_port_protocol = None
            gateway_ip = None
            ufw_managed = None
            traefik_port_num = None
            traefik_passenger_port_num = None
            traefik_passenger_reload_port_num = None

            container_port_dict = container.attrs['NetworkSettings']['Ports'].items()

            if container_network != 'default':
                # compose network
                container_ip = container.attrs['NetworkSettings']['Networks'][container_network]['IPAddress']
                gateway_ip = container.attrs['NetworkSettings']['Networks'][container_network]['Gateway']
            else:
                # default network
                container_ip = container.attrs['NetworkSettings']['Networks']['bridge']['IPAddress']
                gateway_ip = container.attrs['NetworkSettings']['Networks']['bridge']['Gateway']

            if 'UFW_MANAGED' in container.labels:
                ufw_managed = container.labels.get('UFW_MANAGED').capitalize()

            if 'traefik.passenger.port' in container.labels:
                traefik_passenger_port_num = container.labels.get('traefik.passenger.port')

            if 'traefik.port' in container.labels:
                traefik_port_num = container.labels.get('traefik.port')

            if 'traefik.passenger.reload.port' in container.labels:
                traefik_passenger_reload_port_num = container.labels.get('traefik.passenger.reload.port')

            if ufw_managed == 'True':
                for key, value in container_port_dict:
                    if value:
                        container_port_num = list(key.split("/"))[0]
                        container_port_protocol = list(key.split("/"))[1]

            if event_type == 'start' and ufw_managed == 'True':
                for key, value in container_port_dict:
                    if value:
                        container_port_num = list(key.split("/"))[0]
                        container_port_protocol = list(key.split("/"))[1]
                        print(f"Adding UFW rule: {container_port_num}/{container_port_protocol} of container {container.name}")
                        subprocess.run([f"sudo ufw route allow proto {container_port_protocol} \
                                            from any to {container_ip} \
                                            port {container_port_num}"],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                       shell=True)
                        # Example: 172.17.0.1 - host.docker.internal ip address
                        print(f"Adding UFW rule: {container_port_num}/{container_port_protocol} of container {docker_ip}")
                        subprocess.run([f"sudo ufw allow proto {container_port_protocol} \
                                            from any to {docker_ip} \
                                            port {container_port_num}"],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                       shell=True)
                        # Example: 172.19.0.1 - bridge gateway ip address
                        print(f"Adding UFW rule: {container_port_num}/{container_port_protocol} of container {gateway_ip}")
                        subprocess.run([f"sudo ufw allow proto {container_port_protocol} \
                                            from any to {gateway_ip} \
                                            port {container_port_num}"],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                       shell=True)

                if traefik_passenger_port_num:
                    print(f"Adding UFW rule: {traefik_passenger_port_num}/tcp of container {container.name}, {container_ip}")
                    subprocess.run([f"sudo ufw route allow proto tcp \
                                        from any to {container_ip} \
                                        port {traefik_passenger_port_num}"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                shell=True)
                if traefik_port_num:
                    print(f"Adding UFW rule: {traefik_port_num}/tcp of container {container.name}, {container_ip}")
                    subprocess.run([f"sudo ufw route allow proto tcp \
                                        from any to {container_ip} \
                                        port {traefik_port_num}"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                shell=True)
                if traefik_passenger_reload_port_num:
                    print(f"Adding UFW rule: {traefik_passenger_reload_port_num}/tcp of container {container.name}, {container_ip}")
                    print(f"reload port: {traefik_passenger_reload_port_num}")
                    subprocess.run([f"sudo ufw route allow proto tcp \
                                        from any to {container_ip} \
                                        port {traefik_passenger_reload_port_num}"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                shell=True)

            if event_type == 'kill' and ufw_managed == 'True':
                ufw_length = subprocess.run(
                    [f"sudo ufw status numbered | grep {container_ip} | wc -l"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                    shell=True)

                for i in range(int(ufw_length.stdout.strip().split("\n")[0])):
                    awk = "'{print $2}'"
                    ufw_status = subprocess.run(
                        [f"sudo ufw status numbered | grep {container_ip} | awk -F \"[][]\" {awk} "],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                        shell=True)

                    ufw_num = ufw_status.stdout.strip().split("\n")[0]
                    print(f"Cleaning UFW rule: {container_port_num}/{container_port_protocol} of container {container.name}")
                    ufw_delete = subprocess.run([f"yes y | sudo ufw delete {ufw_num}"],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                            shell=True)


if __name__ == '__main__':
    manage_ufw()
