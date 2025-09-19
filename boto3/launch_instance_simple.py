"""
Launch an EC2 instance, including the necessary security group and key pair
setup, and copy the "app" folder to the instance.

Requirements:
- boto3 in your Python environment
- AWS credentials configured (e.g., via AWS CLI or environment variables)
- SSH client installed (for SCP command)
- An "app" folder in the same directory as this script
- Ensure the AMI ID is valid for your AWS region
- Ensure the instance type is available in your AWS region

"""

import boto3
import os
import subprocess

# Configuration
APP_NAME = "XAI_App4"
AMI_ID = "ami-02d7ced41dff52ebc"
INSTANCE_TYPE = "t3.micro"
KEY_NAME = f"{APP_NAME}_key"
SG_NAME = f"{APP_NAME}_SG"
KEY_FILE = f"{KEY_NAME}.pem"

# Display the current region
session = boto3.Session()
print(f"Using AWS region: {session.region_name}")

ec2 = boto3.client("ec2")

# 1. Create a key pair
print("Creating key pair...")
key_pair = ec2.create_key_pair(KeyName=KEY_NAME)
with open(KEY_FILE, "w") as f:
    f.write(key_pair["KeyMaterial"])
os.chmod(KEY_FILE, 0o600)
print(f"Key pair saved to {KEY_FILE}")

# 2. Create security group
print("Creating security group...")
sg = ec2.create_security_group(
    GroupName=SG_NAME,
    Description=f"Security group for {APP_NAME}",
)
sg_id = sg["GroupId"]
print(f"Security Group ID: {sg_id}")

# 3. Authorize inbound rules (HTTP, Dash, SSH)
print("Authorizing inbound rules...")
ec2.authorize_security_group_ingress(
    GroupId=sg_id,
    IpPermissions=[
        {
            "IpProtocol": "tcp", "FromPort": 80, "ToPort": 80,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
        },
        {
            "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
        },
    ]
)

# 4. Launch EC2 instance with 20GB storage
print("Launching EC2 instance...")
instances = ec2.run_instances(
    ImageId=AMI_ID,
    InstanceType=INSTANCE_TYPE,
    KeyName=KEY_NAME,
    SecurityGroupIds=[sg_id],
    MinCount=1,
    MaxCount=1,
    BlockDeviceMappings=[
        {
            'DeviceName': '/dev/sda1',
            'Ebs': {
                'VolumeSize': 20,  # Size in GB
                'VolumeType': 'gp2',
                'DeleteOnTermination': True
            }
        }
    ]
)

instance_id = instances["Instances"][0]["InstanceId"]
print(f"Instance launched: {instance_id}")

# 5. Wait for instance to be running
print("Waiting for instance to be running...")
ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])
print("Instance is running.")

# 6. Wait until status checks are OK
print("Waiting for instance status to be OK...")
ec2.get_waiter("instance_status_ok").wait(InstanceIds=[instance_id])
print("Instance status is OK.")

# 7. Get the public IP
desc = ec2.describe_instances(InstanceIds=[instance_id])
public_ip = desc["Reservations"][0]["Instances"][0]["PublicIpAddress"]
print(f"Public IP: {public_ip}")

# 8. SCP the "app" folder to the instance
print("Copying app folder to instance...")
subprocess.run(
    [
        "scp",
        "-T",
        "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        "-r", "app",
        f"ubuntu@{public_ip}:/home/ubuntu"
    ],
    check=True
)

print("Deployment complete.")
print("Access your instance with SSH as follows:")
print(f"ssh -i {KEY_FILE} ubuntu@{public_ip}")
