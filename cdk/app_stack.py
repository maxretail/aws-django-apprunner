from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    aws_apprunner as apprunner,
    aws_ecr as ecr,
    CfnOutput,
    RemovalPolicy,
    SecretValue,
    Duration,
)
from constructs import Construct
import secrets
import string
import os
import logging
from secrets_manager import SecretManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('AppStack')

class AppStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, app_name: str, **kwargs) -> None:
        if not app_name:
            raise ValueError("app_name parameter is required")
            
        super().__init__(scope, construct_id, **kwargs)

        logger.info(f"Initializing AppStack for app: {app_name}")
        
        # Get superuser email from environment or use default
        superuser_email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'devops@example.com')
        logger.info(f"Using superuser email: {superuser_email}")

        # Initialize our Secret Manager
        logger.info("Initializing Secret Manager")
        secret_manager = SecretManager(self, app_name)
        
        # Automatically discover and load all secret files from the .secrets directory
        # This makes the stack dynamic - just add files to .secrets/ and they'll be included
        logger.info("Discovering secret files")
        secrets_found = secret_manager.discover_and_load_all_secret_files()
        
        # Create Django defaults if no django secret file exists
        # This ensures critical secrets always have sensible defaults
        if 'django' not in secrets_found:
            logger.info("No django secret file found, creating defaults")
            django_defaults = {
                "DJANGO_SECRET_KEY": ''.join(secrets.choice(string.ascii_letters + string.digits + string.punctuation) for _ in range(50)),
                "DJANGO_SUPERUSER_PASSWORD": ''.join(secrets.choice(string.ascii_letters + string.digits + '@#$%^&*') for _ in range(16))
            }
            secret_manager.add_secret_file("django", django_defaults)
            logger.info("Created default django secrets")
        
        # Create the secrets in AWS Secrets Manager
        logger.info("Creating secrets in AWS Secrets Manager")
        app_secrets = secret_manager.create_secrets_in_secrets_manager()
        logger.info(f"Created {len(app_secrets)} secrets in AWS Secrets Manager")

        # Log which secret files were found and will be used
        print(f"Found and loaded {len(secrets_found)} secret files: {', '.join(secrets_found.keys())}")

        # Create VPC
        vpc = ec2.Vpc(
            self, f"{app_name}Vpc",
            max_azs=2,
            nat_gateways=1,
        )

        # Create security group for RDS
        db_security_group = ec2.SecurityGroup(
            self, f"{app_name}DbSecurityGroup",
            vpc=vpc,
            description=f"Security group for {app_name} RDS database",
        )

        # Create security group for App Runner VPC connector
        vpc_connector_sg = ec2.SecurityGroup(
            self, f"{app_name}VpcConnectorSg",
            vpc=vpc,
            description=f"Security group for {app_name} App Runner VPC connector",
        )

        # Allow inbound PostgreSQL traffic from VPC connector to RDS
        db_security_group.add_ingress_rule(
            peer=vpc_connector_sg,
            connection=ec2.Port.tcp(5432),
            description="Allow PostgreSQL traffic from App Runner VPC connector"
        )

        # Create RDS instance with credentials
        db_credentials = rds.Credentials.from_generated_secret(
            "postgres",
            exclude_characters="/@\"'\\"
        )

        db = rds.DatabaseInstance(
            self, f"{app_name}Db",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3,
                ec2.InstanceSize.MICRO
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[db_security_group],
            removal_policy=RemovalPolicy.DESTROY,
            deletion_protection=False,
            database_name=app_name.lower(),
            credentials=db_credentials,
            backup_retention=Duration.days(7),
            monitoring_interval=Duration.seconds(60),
            enable_performance_insights=True,
        )

        # Use existing ECR repository
        ecr_repo = ecr.Repository.from_repository_name(
            self, f"{app_name}Repo",
            repository_name=app_name
        )

        # Create App Runner instance role
        instance_role = iam.Role(
            self, f"{app_name}InstanceRole",
            assumed_by=iam.ServicePrincipal("tasks.apprunner.amazonaws.com"),
        )

        # Create App Runner access role for ECR
        access_role = iam.Role(
            self, f"{app_name}AccessRole",
            assumed_by=iam.ServicePrincipal("build.apprunner.amazonaws.com"),
        )

        # Add ECR pull permissions to access role
        access_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "ecr:GetAuthorizationToken",
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
                "ecr:DescribeImages"
            ],
            resources=["*"]  # GetAuthorizationToken requires resource "*"
        ))

        # Grant minimal permissions to access secrets
        logger.info("Granting permissions to access secrets")
        for secret_name, secret in app_secrets.items():
            secret.grant_read(instance_role)
            logger.info(f"Granted access to secret: {secret_name}")
        db.secret.grant_read(instance_role)
        logger.info("Granted access to database secret")
        ecr_repo.grant_pull(access_role)

        # Create VPC connector
        vpc_connector = apprunner.CfnVpcConnector(
            self, f"{app_name}VpcConnector",
            subnets=[subnet.subnet_id for subnet in vpc.private_subnets],
            security_groups=[vpc_connector_sg.security_group_id],
        )

        # Create App Runner service
        service_name = f"{app_name}Service"
        # App Runner URLs are in the format: {service-id}.{region}.awsapprunner.com
        expected_domain = f".{self.region}.awsapprunner.com"
        
        # We'll use a Token that will be resolved at deployment time
        csrf_origins = [f"https://*{expected_domain}"]
        
        print(f"Setting CSRF_TRUSTED_ORIGINS to: {csrf_origins}")

        # Get environment variables from our app secrets
        logger.info("Getting environment variables from secrets")
        env_vars = secret_manager.get_environment_variables()
        logger.info(f"Got {len(env_vars)} environment variables from secrets")
        
        # Add standard environment variables
        logger.info("Adding standard environment variables")
        standard_env_vars = [
            apprunner.CfnService.KeyValuePairProperty(
                name="DJANGO_SETTINGS_MODULE",
                value="config.settings.production"
            ),
            apprunner.CfnService.KeyValuePairProperty(
                name="DB_NAME",
                value=app_name.lower()
            ),
            apprunner.CfnService.KeyValuePairProperty(
                name="DB_USER",
                value=db.secret.secret_value_from_json("username").to_string()
            ),
            apprunner.CfnService.KeyValuePairProperty(
                name="DB_PASSWORD",
                value=db.secret.secret_value_from_json("password").to_string()
            ),
            apprunner.CfnService.KeyValuePairProperty(
                name="DB_HOST",
                value=db.db_instance_endpoint_address
            ),
            apprunner.CfnService.KeyValuePairProperty(
                name="DB_PORT",
                value=db.db_instance_endpoint_port
            ),
            apprunner.CfnService.KeyValuePairProperty(
                name="CSRF_TRUSTED_ORIGINS",
                value=",".join(csrf_origins)
            ),
            apprunner.CfnService.KeyValuePairProperty(
                name="DJANGO_SUPERUSER_EMAIL",
                value=superuser_email
            ),
        ]
        env_vars.extend(standard_env_vars)
        logger.info(f"Total environment variables: {len(env_vars)}")

        app_runner_service = apprunner.CfnService(
            self, f"{app_name}Service",
            source_configuration=apprunner.CfnService.SourceConfigurationProperty(
                image_repository=apprunner.CfnService.ImageRepositoryProperty(
                    image_identifier=ecr_repo.repository_uri_for_tag(os.environ.get('IMAGE_TAG', 'latest')),
                    image_configuration=apprunner.CfnService.ImageConfigurationProperty(
                        port="8000",
                        start_command="/app/entrypoint.sh",
                        runtime_environment_variables=env_vars
                    ),
                    image_repository_type="ECR",
                ),
                auto_deployments_enabled=True,
                authentication_configuration=apprunner.CfnService.AuthenticationConfigurationProperty(
                    access_role_arn=access_role.role_arn,
                ),
            ),
            health_check_configuration=apprunner.CfnService.HealthCheckConfigurationProperty(
                path="/health/",
                protocol="HTTP",
                interval=10,  # Check every 10 seconds
                timeout=5,    # Wait up to 5 seconds for response
                healthy_threshold=2,  # Number of consecutive successes required
                unhealthy_threshold=3,  # Number of consecutive failures before marking unhealthy
            ),
            instance_configuration=apprunner.CfnService.InstanceConfigurationProperty(
                cpu="2048",
                memory="4096",
                instance_role_arn=instance_role.role_arn,
            ),
            network_configuration=apprunner.CfnService.NetworkConfigurationProperty(
                egress_configuration=apprunner.CfnService.EgressConfigurationProperty(
                    egress_type="VPC",
                    vpc_connector_arn=vpc_connector.attr_vpc_connector_arn,
                ),
            ),
        )

        # Output important values
        CfnOutput(
            self, "DatabaseEndpoint",
            value=db.db_instance_endpoint_address,
            description="Database endpoint address",
        )

        CfnOutput(
            self, "AppRunnerServiceUrl",
            value=app_runner_service.attr_service_url,
            description="App Runner service URL",
        )

        CfnOutput(
            self, "EcrRepositoryUri",
            value=ecr_repo.repository_uri,
            description="ECR repository URI",
        )

        # Get the Django secret ARN for display
        django_secret_name = f"{app_name}_django"
        django_secret = app_secrets.get(django_secret_name)
        django_secret_arn = django_secret.secret_arn if django_secret else "No Django secret found"

        # Add admin login information
        CfnOutput(
            self, "AdminLoginInfo",
            value=(
                "Admin Login Details:\n"
                f"URL: https://{app_runner_service.attr_service_url}/admin\n"
                f"Email: {superuser_email}\n"
                "Username: admin\n"
                f"Password: Get it from Secrets Manager - {django_secret_arn}\n"
                "AWS CLI command to get password:\n"
                f"aws secretsmanager get-secret-value --secret-id {django_secret_arn} --query 'SecretString' --output text | jq -r '.DJANGO_SUPERUSER_PASSWORD'"
            ),
            description="Admin login information"
        ) 