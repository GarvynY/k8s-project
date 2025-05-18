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














# Editing this README

When you're ready to make this README your own, just edit this file and use the handy template below (or feel free to structure it however you want - this is just a starting point!). Thanks to [makeareadme.com](https://www.makeareadme.com/) for this template.

## Suggestions for a good README

Every project is different, so consider which of these sections apply to yours. The sections used in the template are suggestions for most open source projects. Also keep in mind that while a README can be too long and detailed, too long is better than too short. If you think your README is too long, consider utilizing another form of documentation rather than cutting out information.

## Name
Choose a self-explaining name for your project.

## Description
Let people know what your project can do specifically. Provide context and add a link to any reference visitors might be unfamiliar with. A list of Features or a Background subsection can also be added here. If there are alternatives to your project, this is a good place to list differentiating factors.

## Badges
On some READMEs, you may see small images that convey metadata, such as whether or not all the tests are passing for the project. You can use Shields to add some to your README. Many services also have instructions for adding a badge.

## Visuals
Depending on what you are making, it can be a good idea to include screenshots or even a video (you'll frequently see GIFs rather than actual videos). Tools like ttygif can help, but check out Asciinema for a more sophisticated method.

## Installation
Within a particular ecosystem, there may be a common way of installing things, such as using Yarn, NuGet, or Homebrew. However, consider the possibility that whoever is reading your README is a novice and would like more guidance. Listing specific steps helps remove ambiguity and gets people to using your project as quickly as possible. If it only runs in a specific context like a particular programming language version or operating system or has dependencies that have to be installed manually, also add a Requirements subsection.

## Usage
Use examples liberally, and show the expected output if you can. It's helpful to have inline the smallest example of usage that you can demonstrate, while providing links to more sophisticated examples if they are too long to reasonably include in the README.

## Support
Tell people where they can go to for help. It can be any combination of an issue tracker, a chat room, an email address, etc.

## Roadmap
If you have ideas for releases in the future, it is a good idea to list them in the README.

## Contributing
State if you are open to contributions and what your requirements are for accepting them.

For people who want to make changes to your project, it's helpful to have some documentation on how to get started. Perhaps there is a script that they should run or some environment variables that they need to set. Make these steps explicit. These instructions could also be useful to your future self.

You can also document commands to lint the code or run tests. These steps help to ensure high code quality and reduce the likelihood that the changes inadvertently break something. Having instructions for running tests is especially helpful if it requires external setup, such as starting a Selenium server for testing in a browser.

## Authors and acknowledgment
Show your appreciation to those who have contributed to the project.

## License
For open source projects, say how it is licensed.

## Project status
If you have run out of energy or time for your project, put a note at the top of the README saying that development has slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or owner, allowing your project to keep going. You can also make an explicit request for maintainers.
