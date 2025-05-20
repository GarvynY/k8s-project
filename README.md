# COMP_team_43 Project Deployment
+ This readme file is used to help you deploy our Project.


## Getting well prepared 
+ To get started, you may need to prepare for you k8s cluster and prerequisites first

**The prerequistes software used as shown below**

~~~shell
OpenStack clients >= 5.8.x
Please ensure the following Openstack clients are installed: python-cinderclient, python-keystoneclient, python-magnumclient, python-neutronclient, python-novaclient, python-octaviaclient. See: Install the OpenStack client.
JQ >= 1.7.x 
kubectl >= 1.30.0 and < 1.33.0 
Helm >= 3.17.x 
~~~

**cluster**

~~~text
1. a k8s cluster
2. ES cluster (version = 8.5.1)
3. kibana (visualization of ES)
4. Fission (version = 1.21.0)
5. fission client
~~~

**If you need team work in the project**  after start a k8s cluster, you need to connect it by using `openrc.sh` file in the Nectar and share config file with the team members, then they can use export command to put in the `~/.kube/config`, then the cluster  can be connected.


## Deployment
+ we mainly use Mastodon and Bluesky API to request data, so If you need to  have the real data in the cluster, you may need to apply a new accout and token in these two websites.

### Project structure and Files
+ In the root, `.gitignore` file is used to ignore all system files in the `Mac os system` and all temporary files during the runtime 
+ **Test**: all test files, duing the development, includes the simple function test and unit test(like simple ES requests, fission function for sample data)
+ **data**: all sample data are in the folder
+ **backend**: the backend functions are in this dictionary, which includes data harvesting, data refinement and specs
+ **frontend**: the frontend files (ipynb files) run on Jupyter Notebook are in this folder

### Data harvest

+ To get started, you need to harvest data in your ES database first.

#### Mastodon

**Fetch History raw data**

1. After test you can access ES in the cluster, to store the data, we need to create ES index first

+ Port- forward , run `kubectl port-forward service/elasticsearch-master -n elastic 9200:9200` in the terminal, then  keep running and open another one, run

~~~shell
curl -X PUT -k 'https://127.0.0.1:9200/mastodon_election_raw' \
  -u elastic:elastic \
  -H 'Content-Type: application/json' \
  -d '{
    "mappings": {
      "properties": {
        "id":               { "type": "keyword"   },
        "created_at":       { "type": "date"      },
        "post_time_of_day": { "type": "keyword"   },
        "post_day_of_week": { "type": "keyword"   },
        "content":          { "type": "text"      },
        "sentiment_score":  { "type": "float"     },
        "emotion_label":    { "type": "keyword"   },
        "location":         { "type": "keyword"   },
        "geolocation":      { "type": "geo_point" },
        "account":          { "type": "keyword"   },
        "reblogs_count":    { "type": "integer"   },
        "favourites_count": { "type": "integer"   },
        "url":              { "type": "keyword"   }
      }
    }
  }'
~~~

+ Check if it was succeeded 

~~~shell
curl -X GET -k 'https://127.0.0.1:9200/mastodon_election_raw?pretty' \
-u elastic:elastic
~~~

2. You need to deploy the fission function to ingest the Mastodon data needed

+  `cd backend/harverst/mastodon-harvest`
+ To be more stable and fast, we pre-download the dependencies that function needed and then upload them with package

~~~shell
mkdir vendor && pip install -r requirements.txt -t vendor
~~~

+ Using zip to pack 

~~~shell
zip -r mastodon-ingest-6m.zip requirements.txt vendor mastodon-ingest-v2-aus.py
~~~

+ upload package

~~~shell
fission package create --name mastodon-ingest-6m-pkg --env python39x --sourcearchive mastodon-ingest-6m.zip --namespace default --buildcmd ""
# check
fission package list
~~~

+ create package by package(after package building succeeded) and use newdeploy mode (easy for monitoring and testing)

~~~shell
fission fn create --name mastodon-ingest-6m --env python39x --namespace default --pkg mastodon-ingest-6m-pkg --entrypoint "mastodon-ingest-v2-aus.main" --executortype newdeploy --minscale 1 --maxscale 1
~~~

+ run function once(this function is used to fetch history data)

~~~shell
fission fn test --name mastodon-ingest-6m
~~~

+ Check data 

~~~shell
curl -k -u elastic:elastic 'https://127.0.0.1:9200/mastodon_election_raw/_count?pretty'
~~~

**Set scheduled task to update raw data**

1. We need a scheduled task to fetch the latest data, so that we can see the new data in the ES database, first a update fission function is needed

+ create zip file

~~~shell
zip -r mastodon-ingest-update.zip requirements.txt vendor mastodon-scheduled-update-v2.py
~~~

+ create package and upload

~~~shell
fission package create --name mastodon-ingest-update-pkg  --env python39x --sourcearchive mastodon-ingest-update.zip --namespace default --buildcmd ""
~~~

+ Create fission function

~~~shell
fission fn create --name mastodon-ingest-update --env python39x --namespace default --pkg mastodon-ingest-update-pkg --entrypoint "mastodon-scheduled-update-v2.main" --executortype newdeploy --minscale 1 --maxscale 1
~~~

2. We need a timetrigger using cron to activate the function every x minutes, so we can fetch the latest data

+ create trigger 

~~~shell
fission timetrigger create \
  --name mastodon-update \
  --function mastodon-ingest-update \
  --cron "@every 1h" # this time can change
~~~

+ check log (if the function can be triggered)

~~~shell
fission fn log --name mastodon-ingest-update
~~~



#### BlueSky

**Get data with refreshment**

1. Create ES index using kibana Devtools

+ set portfoward to login kibana

~~~shell
kubectl port-forward service/kibana-kibana -n elastic 5601:5601
~~~

+ set es index in Devtools

~~~shell
PUT bluesky_zy
"mappings": {
    "properties": {
      "uri": {
        "type": "keyword"
      },
      "created_at": {
        "type": "date",
        "format": "strict_date_time"
      },
      "post_time_of_day": {
        "type": "keyword"
      },
      "post_day_of_week": {
        "type": "keyword"
      },
      "content": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "sentiment_score": {
        "type": "float"
      },
      "emotion_label": {
        "type": "keyword"
      },
      "author": {
        "type": "keyword"
      },
      "location": {
        "type": "keyword"
      },
      "geolocation": {
        "type": "geo_point"
      }
    }
  }
}
~~~
+ Check if it was succeeded 

~~~shell
curl -X GET -k 'https://127.0.0.1:9200/bluesky_zy?pretty' \
-u elastic:elastic
~~~

2. Deploy the fission function and timetrigger like mastodon above




### Data refinement

+ In the first step, we only harvest the raw data with the simple data preprocessing process, but we may need data with different granularities, then some data aggregation or refinement action is needed.

#### Mastodon

**History data update**

1. To store the data after refinement, we need a new index

+ port forward: run `kubectl port-forward service/elasticsearch-master -n elastic 9200:9200` in the terminal, then  keep running and open another one, run

~~~shell
curl -X PUT -k 'https://127.0.0.1:9200/election_analysis' \
  -u elastic:elastic \
  -H 'Content-Type: application/json' \
  -d '
{
  "mappings": {
    "properties": {
      "created_at": {
        "type":   "date",
        "format": "strict_date_optional_time||epoch_millis"
      },
      "sentiment_score": {
        "type": "float"
      },
      "emotion_label": {
        "type": "keyword"
      },
      "location": {
        "type": "keyword"
      },
      "geolocation": {
        "type": "geo_point"
      },
      "post_time_of_day": {
        "type": "keyword"
      }
    }
  }
}
'

curl -X PUT -k 'https://127.0.0.1:9200/election_v2' \
  -u elastic:elastic \
  -H 'Content-Type: application/json' \
  -d '
{
  "mappings": {
    "properties": {
      "created_at": {
        "type":   "date",
        "format": "strict_date_optional_time||epoch_millis"
      },
      "sentiment_score": {
        "type": "float"
      },
      "emotion_label": {
        "type": "keyword"
      },
      "location": {
        "type": "keyword"
      },
      "geolocation": {
        "type": "geo_point"
      },
      "post_time_of_day": {
        "type": "keyword"
      },
      "content": {
        "type":     "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
'
~~~

+ Check if it was succeeded 

~~~shell
curl -X GET -k 'https://127.0.0.1:9200/<index name>?pretty' \
-u elastic:elastic
~~~

2. We need to process the data already existed in the ES database
   + `cd backend/data_refine/masto-refine`

+ create zip package

~~~shell
mkdir vendor && pip3 install -r requirements.txt -t vendor
zip -r  masto-analysis.zip requirements.txt vendor masto-analysis.py
zip -r  masto-analysis-v2.zip requirements.txt vendor masto-analysis-v2.py
~~~

+ create package and upload 

~~~shell
fission package create --name masto-analysis-pkg  --env python39x --sourcearchive  masto-analysis.zip  --namespace default --buildcmd ""
fission package create --name masto-analysis-v2-pkg  --env python39x --sourcearchive  masto-analysis-v2.zip  --namespace default --buildcmd ""
fission package list
~~~

+ create fission function (after package building succeed)

~~~shell
fission fn create --name masto-analysis --env python39x --namespace default --pkg masto-analysis-pkg --entrypoint "masto-analysis.main" --executortype newdeploy --minscale 1 --maxscale 1
fission fn create --name masto-analysis-v2 --env python39x --namespace default --pkg masto-analysis-v2-pkg --entrypoint "masto-analysis-v2.main" --executortype newdeploy --minscale 1 --maxscale 1
~~~

+ Run

~~~shell
fission function test --name masto-analysis
fission function test --name masto-analysis-v2
~~~

**Scheduled data update**

+ As we update the raw data in a scheduled task, so we need process the updated data in time by a scheduled function

+ create zip file

~~~shell
 zip -r  masto-analysis-incremental.zip requirements.txt vendor masto-analysis-incremental.py
~~~

+ Create package

~~~shell
fission package create --name masto-analysis-incremental-pkg  --env python39x --sourcearchive  masto-analysis-incremental.zip  --namespace default --buildcmd ""
~~~

+ create fission function

~~~shell
fission fn create --name masto-analysis-incremental --env python39x --namespace default --pkg masto-analysis-incremental-pkg --entrypoint "masto-analysis-incremental.main" --executortype newdeploy --minscale 1 --maxscale 1
~~~

+ Create timetrigger

~~~shell
  fission timetrigger create \
  --name mastodon-analysis-update \
  --function masto-analysis-incremental \
  --cron "@every 1h" # this time is dependent on the raw data fetch speed
~~~

#### BlueSky

+ the same way like Mastodon Above

### function and package list during Deployment
+ functions list
~~~shell
NAME                                                   USAGE
bluesky-v2                                                            
health                                                                 
healthcm                                                 
hello                                                              
masto-analysis                                                             
masto-analysis-incremental                                              
masto-analysis-v2                                                           
masto-es-test                                                            
masto-harvest-unit-test                                                               
mastodon-ingest-6m                                                                       
mastodon-ingest-update                                 
python39x                                             
reddit                                              
zy-bluesky                                           
zy-datatrans-v2               
~~~

+ packasges list
~~~shell
NAME                                                   USAGE
masto-analysis-v2-pkg                                    
zy-datatrans-v2-pkg                            
masto-analysis-incremental-pkg                 
masto-analysis-pkg                             
zy-bluesky-v2-pkg                              
mastodon-ingest-update-pkg                     
reddit-pkg                                     
mastodon-ingest-6m-pkg                         
zy-bluesky-pkg                                 
masto-harvest-unit-test-pkg                   
masto-es-test-zy-pkg                           
masto-es-test-pkg                              
masto-get-zy                                   
mas-test-hard                                 
mas-test-pkg                                   
python39x-d2770f74-862c-4b3a-8a08-f2b7c1d3a321 
healthcm-3293778d-7e14-419d-879f-9fa4ca6c7139  
health-5d03a002-b391-46a5-bdbc-479942b1c13a    
hello-e0170c40-382e-466d-a474-3f70efc2214e    
health-49f8e8cb-6883-4aef-8e09-65a9b61b86a7    
~~~

### Data visualisation

#### Jupyter Notebook Deployment

+ After the cluster and the data is well prepared, we can use Jupyter Notebook to visualize and analyze them. In this project, no PVC notebook and git persistence will be used

1. add notebook namespace 

~~~shell
kubectl create namespace notebook
~~~

2. add helm Jupyter notebook repo

~~~shell
helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm repo update
~~~

3. Test connection between notebook namespace and ES

+ start interactive console base on notebook namespace

~~~shell
kubectl run debug-curl \
  --image=curlimages/curl \
  --restart=Never \
  -it \
  -n notebook \
  -- sh
~~~

+ test 

~~~shell
  curl -sk -u elastic:elastic \
  "https://elasticsearch-master.elastic.svc.cluster.local:9200/_cluster/health?pretty"
~~~

4. Get git token in the Gitlab project, so we can update work tree in the notebook and implement persistence, the token should be read only, so that we can test locally and deploy the stable project.

+ After get token, we create a secret yaml file and a fission secret

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: gitlab-credentials
  namespace: notebook
type: Opaque
data:
  secret:<Your token>
~~~

~~~shell
kubectl create secret generic gitlab-credentials \
  --namespace notebook \
  --from-literal=secret=gitlab-credentials
~~~

5. create a notebook and using the secret to pull git repo every 30s

~~~yaml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: notebook-git-demo
  namespace: notebook
spec:
  replicas: 1
  selector:
    matchLabels:
      app: notebook-git-demo
  template:
    metadata:
      labels:
        app: notebook-git-demo
    spec:
      volumes:
        - name: workspace
          emptyDir: {}
        - name: site-packages
          emptyDir: {}
      initContainers:
        - name: git-sync
          image: k8s.gcr.io/git-sync/git-sync:v3.2.2
          env:
            - name: GIT_SYNC_REPO
              value: "https://gitlab.unimelb.edu.au/ygao3631/comp_team_43.git"
            - name: GIT_SYNC_BRANCH
              value: "main"
            - name: GIT_SYNC_ROOT
              value: "/git"
            - name: GIT_SYNC_DEST
              value: "repo"
            - name: GIT_SYNC_ONE_TIME
              value: "false"
            - name: GIT_SYNC_WAIT
              value: "30"
            - name: GIT_SYNC_USERNAME
              valueFrom:
                secretKeyRef:
                  name: gitlab-credentials
                  key: username
            - name: GIT_SYNC_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: gitlab-credentials
                  key: password
          volumeMounts:
            - name: workspace
              mountPath: /git
        - name: deps-install
          image: jupyter/base-notebook:latest
          command:
            - sh
            - -c
            - |
              set -e
              cd /git/repo/frontend
              pip install --no-index \
                --find-links=deps \
                --target=/opt/conda/lib/python3.11/site-packages \
                -r requirements.txt
          volumeMounts:
            - name: workspace
              mountPath: /git
            - name: site-packages
              mountPath: /opt/conda/lib/python3.11/site-packages
      containers:
        - name: notebook
          image: jupyter/base-notebook:latest
          command:
            - start-notebook.sh
            - "--NotebookApp.token=comp_team_43"
          ports:
            - containerPort: 8888
          volumeMounts:
            - name: workspace
              mountPath: /home/jovyan/work
            - name: site-packages
              mountPath: /opt/conda/lib/python3.11/site-packages
---
apiVersion: v1
kind: Service
metadata:
  name: notebook-git-demo
  namespace: notebook
spec:
  selector:
    app: notebook-git-demo
  ports:
    - port: 8888
      targetPort: 8888
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: notebook-git-demo
  namespace: notebook
  annotations:
    nginx.ingress.kubernetes.io/use-regex: "true"
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  ingressClassName: nginx
  rules:
    - host: jupyter.elec-analysis.com
      http:
        paths:
          - path: /demo(/|$)(.*)
            pathType: ImplementationSpecific
            backend:
              service:
                name: notebook-git-demo
                port:
                  number: 8888
~~~

6. apply yaml

~~~shell
cd frontend/demo_config
kubectl apply -f notebook-git-demo.yaml
~~~

7. Access notebook

~~~shell
kubectl port-forward svc/notebook-git-demo 8888:8888 -n notebook
http://localhost:8888/?token=comp_team_43
~~~

