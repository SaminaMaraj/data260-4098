#!/usr/bin/env bash
# HW8: create the seven s4098 topics with the Kafka CLI inside the broker container.
#   bash code/hw8/create_topics.sh
set -euo pipefail
echo "Kazi Samina Maraj Mumu | create_topics.sh | PREFIX=s4098"
KT="docker exec s4098-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092"

create() {  # name partitions
  $KT --create --if-not-exists --topic "$1" --partitions "$2" --replication-factor 1
}

# Part 1 request/response
create s4098_entity_requests 1
create s4098_entity_responses 1
# Part 2 agent pipeline (tasks has 2 partitions for the Part 3 ordering test)
create s4098_inbox 1
create s4098_tasks 2
create s4098_drafts 1
create s4098_final 1
# Part 3 dead-letter topic
create s4098_dead_letter 1

echo
$KT --list | grep '^s4098_'
echo
$KT --describe --topic s4098_tasks
