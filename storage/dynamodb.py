"""DynamoDB repository. Inject a boto3 Table (PK/SK string keys).

Optimistic event versions and retry receipts are committed atomically.
Query pagination is mandatory; event IDs remain stable across corrected timestamps.
"""
from storage.attribution import apply_attribution
import json
import uuid
from datetime import timezone
from cat_health_signals import timestamp
from .repository import StorageError


def partition(household, cat_id):
    return json.dumps([household, cat_id], separators=(',', ':'))


class DynamoDBRepository:
    def __init__(self, table):
        self.table = table

    def list_cats(self, household):
        kwargs = dict(KeyConditionExpression='PK = :pk AND begins_with(SK, :prefix)',
                      ExpressionAttributeValues={':pk': partition(household, '__cats__'), ':prefix': 'CAT#'}, ConsistentRead=True)
        cats = []
        while True:
            page = self.table.query(**kwargs)
            cats.extend(json.loads(item['body']) for item in page.get('Items', []))
            if not page.get('LastEvaluatedKey'):
                break
            kwargs['ExclusiveStartKey'] = page['LastEvaluatedKey']
        return sorted(cats, key=lambda cat: (cat['name'].casefold(), cat['cat_id']))

    def get_cat(self, household, cat_id):
        item = self.table.get_item(Key={'PK': partition(household, cat_id), 'SK': 'PROFILE'}, ConsistentRead=True).get('Item')
        if not item:
            raise StorageError('not_found', 'Cat not found in this household')
        return json.loads(item['body'])

    def list_events(self, household, cat_id):
        self.get_cat(household, cat_id)
        kwargs = dict(KeyConditionExpression='PK = :pk AND begins_with(SK, :prefix)', ExpressionAttributeValues={':pk': partition(household, cat_id), ':prefix': 'EVENT#'}, ConsistentRead=True)
        items = []
        while True:
            page = self.table.query(**kwargs)
            items.extend(json.loads(item['body']) for item in page.get('Items', []))
            if not page.get('LastEvaluatedKey'):
                break
            kwargs['ExclusiveStartKey'] = page['LastEvaluatedKey']
        return sorted(items, key=lambda e: (timestamp(e['occurred_at']), e['event_id']))

    def mutate(self, household, tool, args, now):
        from .validation import validate_details
        from server.contracts import profile_changes
        if tool.startswith('log_'):
            validate_details(args['event_type'], args.get('details', {}))
        now = timestamp(now).astimezone(timezone.utc)
        request = json.dumps([tool, args], sort_keys=True)
        key = args.get('idempotency_key')
        retry_key = {'PK': partition(household, '__retries__'), 'SK': 'RETRY#'+key} if key else None
        if retry_key:
            old = self.table.get_item(Key=retry_key, ConsistentRead=True).get('Item')
            if old:
                if old['request'] != request:
                    raise StorageError('idempotency_conflict', 'Retry key already used for different input')
                return json.loads(old['body'])
        cat_id = str(uuid.uuid4()) if tool == 'add_cat' else args['cat_id']
        pk = partition(household, cat_id)
        if tool != 'add_cat':
            self.get_cat(household, cat_id)
        if tool in ('add_cat', 'update_cat'):
            item_key = dict(PK=pk, SK='PROFILE')
            body = dict(cat_id=cat_id, **profile_changes(args) if tool == 'add_cat' else {})
        else:
            event_id = args.get('event_id') or str(uuid.uuid4())
            item_key = dict(PK=pk, SK='EVENT#'+event_id)
            body = dict(event_id=event_id, cat_id=cat_id, kind=tool, event_type=args['event_type'], source=args.get('source', 'user'), recorded_at=now.isoformat(), occurred_at=now.isoformat(), time_defaulted=True, details={}, reporter=None)
        old = self.table.get_item(Key=item_key, ConsistentRead=True).get('Item')
        version = int(old.get('version', 0)) if old else 0
        if tool == 'update_cat':
            if not old:
                raise StorageError('not_found', 'Cat not found in this household')
            body = dict(cat_id=cat_id, **profile_changes(args, json.loads(old['body'])))
        if tool.startswith('log_'):
            if args.get('event_id') and not old:
                raise StorageError('not_found', 'Event not found for this cat and household')
            if old:
                body = json.loads(old['body'])
            if body['kind'] != tool or body['event_type'] != args['event_type'] or body['source'] != args.get('source', 'user'):
                raise StorageError('event_conflict', 'Follow-up must preserve type, kind and source')
            if args.get('occurred_at'):
                occurred = timestamp(args['occurred_at']).astimezone(timezone.utc)
                if occurred > now:
                    raise StorageError('invalid_time', 'Occurrence cannot be in the future')
                body.update(occurred_at=occurred.isoformat(), time_defaulted=False)
            body['details'].update(args.get('details', {}))
            if args.get('reporter') is not None:
                body['reporter'] = args['reporter']
            apply_attribution(body,args,now)
            body['updated_at'] = now.isoformat()
        put = dict(TableName=self.table.name, Item={**item_key, 'body': json.dumps(body), 'version': version+1}, ConditionExpression='attribute_not_exists(PK)' if not old else '#v = :v')
        if old:
            put.update(ExpressionAttributeNames={'#v': 'version'}, ExpressionAttributeValues={':v': version})
        actions = [{'Put': put}]
        if tool in ('add_cat', 'update_cat'):
            actions.append({'Put': dict(TableName=self.table.name, Item={
                'PK': partition(household, '__cats__'), 'SK': 'CAT#'+cat_id, 'body': json.dumps(body)})})
        if retry_key:
            actions.append({'Put': dict(TableName=self.table.name, Item={**retry_key, 'request': request, 'body': json.dumps(body)}, ConditionExpression='attribute_not_exists(PK)')})
        try:
            self.table.meta.client.transact_write_items(TransactItems=actions)
        except Exception as error:
            # Only transaction cancellation can represent an optimistic conflict.
            if getattr(error, 'response', {}).get('Error', {}).get('Code') != 'TransactionCanceledException':
                raise
            if retry_key:
                receipt = self.table.get_item(Key=retry_key, ConsistentRead=True).get('Item')
                if receipt and receipt['request'] == request:
                    return json.loads(receipt['body'])
                if receipt:
                    raise StorageError('idempotency_conflict', 'Retry key already used for different input') from error
            raise StorageError('write_conflict', 'Concurrent change; retry the request') from error
        return body
