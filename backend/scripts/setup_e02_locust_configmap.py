"""
Script to create the ConfigMap dpbps-locust-e02 and patch deployment/loadgenerator
to mount it at /loadgen/locustfile.py while keeping replicas strictly at 0.
"""

from pathlib import Path
from kubernetes import client
from backend.scaling.kubernetes.client import get_apps_v1_api, get_core_v1_api
from backend.workload.profiles import get_gradual_traffic_increase_profile
from backend.workload.shape_generator import generate_combined_locustfile


NAMESPACE = "online-boutique"
CONFIGMAP_NAME = "dpbps-locust-e02"
BASE_LOCUSTFILE = Path("D:/CIS/microservices-demo/src/loadgenerator/locustfile.py")


def main():
    print("Setting up ConfigMap and Deployment mount for E02 (DRY / REPLICAS=0)...")

    core_api = get_core_v1_api()
    apps_api = get_apps_v1_api()

    # 1. Generate combined locustfile
    profile = get_gradual_traffic_increase_profile()
    combined_code = generate_combined_locustfile(BASE_LOCUSTFILE, profile)
    print(f"Generated combined locustfile: {len(combined_code)} bytes.")

    # 2. Create or update ConfigMap in online-boutique
    cm_body = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=CONFIGMAP_NAME,
            namespace=NAMESPACE,
            labels={"app": "loadgenerator", "dpbps.experiment": "e02"},
        ),
        data={"locustfile.py": combined_code},
    )

    try:
        existing_cm = core_api.read_namespaced_config_map(name=CONFIGMAP_NAME, namespace=NAMESPACE)
        core_api.replace_namespaced_config_map(name=CONFIGMAP_NAME, namespace=NAMESPACE, body=cm_body)
        print(f"Successfully updated ConfigMap '{CONFIGMAP_NAME}' in namespace '{NAMESPACE}'.")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            core_api.create_namespaced_config_map(namespace=NAMESPACE, body=cm_body)
            print(f"Successfully created ConfigMap '{CONFIGMAP_NAME}' in namespace '{NAMESPACE}'.")
        else:
            raise

    # 3. Patch deployment/loadgenerator to mount the ConfigMap at /loadgen/locustfile.py
    # Ensure replicas remains 0!
    dep_patch = {
        "spec": {
            "replicas": 0,
            "template": {
                "spec": {
                    "volumes": [
                        {
                            "name": "locustfile-volume",
                            "configMap": {
                                "name": CONFIGMAP_NAME,
                                "items": [{"key": "locustfile.py", "path": "locustfile.py"}],
                            },
                        }
                    ],
                    "containers": [
                        {
                            "name": "main",
                            "volumeMounts": [
                                {
                                    "name": "locustfile-volume",
                                    "mountPath": "/loadgen/locustfile.py",
                                    "subPath": "locustfile.py",
                                }
                            ],
                            "env": [
                                {"name": "FRONTEND_ADDR", "value": "frontend:80"},
                                {"name": "USERS", "value": "50"},
                                {"name": "RATE", "value": "2"},
                            ],
                        }
                    ],
                }
            },
        }
    }

    patched = apps_api.patch_namespaced_deployment(
        name="loadgenerator",
        namespace=NAMESPACE,
        body=dep_patch,
    )
    print(f"Successfully patched deployment/loadgenerator in '{NAMESPACE}'.")
    print(f"Current replicas: {patched.spec.replicas}")
    assert patched.spec.replicas == 0, "Safety violation: replicas must be 0!"
    print("Safety confirmed: loadgenerator replicas is 0.")


if __name__ == "__main__":
    main()

