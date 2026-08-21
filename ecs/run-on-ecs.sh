#!/bin/bash
# Run spdtest.py from a throwaway Aliyun ECS instance (region = hk|sz), then delete it.
# Usage:  source ~/.oss_creds && ./run-on-ecs.sh hk [ssh-private-key-path]
set -euo pipefail
REGION_ALIAS="${1:-hk}"
KEY="${2:-$HOME/amtk/keys/pi-key}"
case "$REGION_ALIAS" in
  hk) REGION=cn-hongkong  VSW=vsw-j6cd7gidpu0w7iwaz7gjc SG=sg-j6calbd0m7fsrrg7c3r1 KP=smoke-hk-key ;;
  sz) REGION=cn-shenzhen  VSW=vsw-wz9r3h2jcmzj7zaysmc26 SG=sg-wz9gqlg5cz2cs2ujrahx KP=smoke-speed-key ;;
  *) echo "usage: $0 hk|sz [key]"; exit 1 ;;
esac
export ALIBABA_CLOUD_ACCESS_KEY_ID="${ALIBABA_CLOUD_ACCESS_KEY_ID:-$OSS_ACCESS_KEY_ID}"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="${ALIBABA_CLOUD_ACCESS_KEY_SECRET:-$OSS_ACCESS_KEY_SECRET}"
R="--mode EnvironmentVariable --region $REGION --RegionId $REGION"
IID=$(aliyun ecs RunInstances $R --InstanceType ecs.e-c1m1.large \
  --ImageId aliyun_3_x64_20G_alibase_20240819.vhd --VSwitchId $VSW --SecurityGroupId $SG \
  --KeyPairName $KP --InstanceChargeType PostPaid --InternetMaxBandwidthOut 100 \
  --InternetChargeType PayByTraffic --SystemDisk.Category cloud_essd_entry --SystemDisk.Size 20 \
  --InstanceName spdtest-tmp | python3 -c "import json,sys; print(json.load(sys.stdin)['InstanceIdSets']['InstanceIdSet'][0])")
trap 'aliyun ecs DeleteInstance $R --InstanceId $IID --Force true >/dev/null; echo "instance $IID deleted"' EXIT
echo "instance: $IID (auto-deleted on exit)"
IP=""
for i in $(seq 1 30); do
  ST=$(aliyun ecs DescribeInstances $R --InstanceIds "[\"$IID\"]" | python3 -c "
import json,sys
d=json.load(sys.stdin)['Instances']['Instance'][0]
ips=d.get('PublicIpAddress',{}).get('IpAddress',[])
print(d['Status'], ips[0] if ips else '')")
  set -- $ST; [ "$1" = "Running" ] && [ -n "${2:-}" ] && IP=$2 && break
  sleep 10
done
[ -n "$IP" ] || { echo "instance never got a public ip"; exit 1; }
echo "ip: $IP"; sleep 20
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $KEY"
scp $SSH_OPTS "$(dirname "$0")/../spdtest.py" root@$IP:/tmp/spdtest.py
ssh $SSH_OPTS root@$IP "python3 /tmp/spdtest.py"
