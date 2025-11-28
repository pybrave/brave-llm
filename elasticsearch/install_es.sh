docker run --rm    \
    --name elasticsearch   \
    -p 9200:9200   -p 9300:9300   \
    -e discovery.type=single-node   \
    -e xpack.security.enabled=false   \
    -e ES_JAVA_OPTS="-Xms512m -Xmx512m"   \
    -v /opt/llm/elasticsearch:/usr/share/elasticsearch/data  \
     docker.elastic.co/elasticsearch/elasticsearch:9.2.1


docker run --rm    \
    --name kibana   \
    -p 5601:5601   \
    -e ELASTICSEARCH_HOSTS=http://192.168.3.63:9200   \
    docker.elastic.co/kibana/kibana:9.2.1