import boto3
import os
import subprocess
import logging

# Configuration
APP_NAME = "XAI_App2"
AMI_ID = "ami-02d7ced41dff52ebc"
INSTANCE_TYPE = "t3.micro"
KEY_NAME = "pair.key"
SG_NAME = f"{APP_NAME}_SG"
KEY_FILE = f"deployments/{APP_NAME}/{KEY_NAME}"

# --- Create filesystem ---
if not os.path.exists(f'deployments/{APP_NAME}'):
    os.makedirs(f'deployments/{APP_NAME}')

# --- Logging Setup ---
# Create a logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create handlers
# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
# File handler
file_handler = logging.FileHandler(f'deployments/{APP_NAME}/deployment.log')
file_handler.setLevel(logging.INFO)

# Create a formatter and set it for both handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# --- AWS Operations ---
try:
    # Display the current region
    session = boto3.Session()
    logger.info(f"Using AWS region: {session.region_name}")

    ec2 = boto3.client("ec2")

    # 1. Create a key pair
    logger.info("Creating key pair...")
    key_pair = ec2.create_key_pair(KeyName=KEY_NAME)
    with open(KEY_FILE, "w") as f:
        f.write(key_pair["KeyMaterial"])
    os.chmod(KEY_FILE, 0o600)
    logger.info(f"Key pair saved to {KEY_FILE}")

    # 2. Create security group
    logger.info("Creating security group...")
    sg = ec2.create_security_group(
        GroupName=SG_NAME,
        Description=f"Security group for {APP_NAME}",
    )
    sg_id = sg["GroupId"]
    logger.info(f"Security Group ID: {sg_id}")

    # 3. Authorize inbound rules (HTTP, Dash, SSH)
    logger.info("Authorizing inbound rules...")
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
    logger.info("Launching EC2 instance...")
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
    logger.info(f"Instance launched: {instance_id}")

    # 5. Wait for instance to be running
    logger.info("Waiting for instance to be running...")
    ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])
    logger.info("Instance is running.")

    # 6. Wait until status checks are OK
    logger.info("Waiting for instance status to be OK...")
    ec2.get_waiter("instance_status_ok").wait(InstanceIds=[instance_id])
    logger.info("Instance status is OK.")

    # 7. Get the public IP
    desc = ec2.describe_instances(InstanceIds=[instance_id])
    public_ip = desc["Reservations"][0]["Instances"][0]["PublicIpAddress"]
    logger.info(f"Public IP: {public_ip}")

    # 8. SCP the "app" folder to the instance
    logger.info("Copying app folder to instance...")
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
    logger.info("Deployment complete.")
    logger.info(f"Access your instance with SSH as follows:\nssh -i {KEY_FILE} ubuntu@{public_ip}")

except Exception as e:
    logger.error(f"An error occurred: {e}")