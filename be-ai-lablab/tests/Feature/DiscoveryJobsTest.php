<?php

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

uses(RefreshDatabase::class);

beforeEach(function () {
    config(['services.ai.url' => 'http://ai.internal:8000', 'services.ai.timeout' => 180]);
    Http::preventStrayRequests();
});

test('discovery returns immediately and polling retrieves a search that takes over 120 seconds', function () {
    $result = [
        'query' => 'macbook', 'total_discovered' => 3, 'total_deduplicated' => 3,
        'total_verified' => 1, 'execution_time_seconds' => 130,
        'provider_used' => 'amd', 'recommendations' => [],
    ];
    Http::fake(['ai.internal:8000/api/v1/discover' => function () use ($result) {
        $this->travel(130)->seconds();

        return Http::response($result);
    }]);

    $response = $this->postJson('/api/v1/discover/jobs', ['query' => 'macbook', 'country' => ' ID '])
        ->assertAccepted()->assertJsonPath('status', 'queued');
    $id = $response->json('id');
    expect(Str::isUuid($id))->toBeTrue();
    Http::assertNothingSent();
    $this->assertDatabaseCount('jobs', 1);
    $this->getJson('/api/v1/discover/jobs/'.$id)->assertOk()->assertJsonPath('status', 'queued');

    Artisan::call('queue:work', ['connection' => 'discovery', '--queue' => 'discovery', '--once' => true, '--sleep' => 0]);

    $this->assertDatabaseCount('jobs', 0);
    $this->getJson('/api/v1/discover/jobs/'.$id)->assertOk()->assertExactJson([
        'status' => 'completed', 'result' => $result,
    ])->assertHeader('Cache-Control', 'no-store, private');
    Http::assertSent(fn ($request) => $request->data() === ['query' => 'macbook', 'country' => 'id']);
});

test('background searches sanitize upstream failures', function (int $status, int $expected) {
    Http::fake(['ai.internal:8000/api/v1/discover' => Http::response(['detail' => 'PRIVATE_DETAIL'], $status)]);
    $id = $this->postJson('/api/v1/discover/jobs', ['query' => 'keyboard'])->assertAccepted()->json('id');

    Artisan::call('queue:work', ['connection' => 'discovery', '--queue' => 'discovery', '--once' => true, '--sleep' => 0]);

    $this->getJson('/api/v1/discover/jobs/'.$id)->assertOk()->assertExactJson([
        'status' => 'failed', 'error_status' => $expected,
    ]);
})->with([[402, 402], [429, 429], [500, 502]]);

test('background searches report connection failures without leaving polling pending', function () {
    Http::fake(['ai.internal:8000/api/v1/discover' => Http::failedConnection()]);
    $id = $this->postJson('/api/v1/discover/jobs', ['query' => 'keyboard'])->assertAccepted()->json('id');

    Artisan::call('queue:work', ['connection' => 'discovery', '--queue' => 'discovery', '--once' => true, '--sleep' => 0]);

    $this->getJson('/api/v1/discover/jobs/'.$id)->assertOk()->assertExactJson([
        'status' => 'failed', 'error_status' => 503,
    ]);
});

test('background search input is validated before enqueueing', function () {
    $this->postJson('/api/v1/discover/jobs', ['query' => 'a'])
        ->assertUnprocessable()->assertJsonValidationErrors('query');
    $this->assertDatabaseCount('jobs', 0);
    Http::assertNothingSent();
});

test('unknown and malformed search identifiers return 404', function () {
    $this->getJson('/api/v1/discover/jobs/'.Str::uuid())->assertNotFound();
    $this->getJson('/api/v1/discover/jobs/not-a-uuid')->assertNotFound();
});

test('search results expire instead of remaining available indefinitely', function () {
    $id = $this->postJson('/api/v1/discover/jobs', ['query' => 'keyboard'])->assertAccepted()->json('id');
    $this->travel(61)->minutes();

    $this->getJson('/api/v1/discover/jobs/'.$id)->assertNotFound();
});

test('search processing state is visible while the worker calls AI', function () {
    $id = $this->postJson('/api/v1/discover/jobs', ['query' => 'keyboard'])->assertAccepted()->json('id');
    Http::fake(['ai.internal:8000/api/v1/discover' => function () use ($id) {
        expect(Cache::store('database')->get('discovery:'.$id))->toBe(['status' => 'processing']);

        return Http::response(['recommendations' => []]);
    }]);

    Artisan::call('queue:work', ['connection' => 'discovery', '--queue' => 'discovery', '--once' => true, '--sleep' => 0]);
    $this->getJson('/api/v1/discover/jobs/'.$id)->assertOk()->assertJsonPath('status', 'completed');
});

test('queue visibility exceeds the AI request timeout', function () {
    expect(config('queue.connections.discovery.retry_after'))->toBeGreaterThan(config('services.ai.timeout') + 10);
});

test('worker exceptions become failed searches instead of leaving processing forever', function () {
    Http::fake(['ai.internal:8000/api/v1/discover' => function () {
        throw new RuntimeException('PRIVATE_DETAIL');
    }]);
    $id = $this->postJson('/api/v1/discover/jobs', ['query' => 'keyboard'])->assertAccepted()->json('id');

    Artisan::call('queue:work', ['connection' => 'discovery', '--queue' => 'discovery', '--once' => true, '--sleep' => 0]);

    $this->getJson('/api/v1/discover/jobs/'.$id)->assertOk()->assertExactJson([
        'status' => 'failed', 'error_status' => 503,
    ]);
    $this->assertDatabaseCount('jobs', 0);
    $this->assertDatabaseCount('failed_jobs', 1);
});

test('expired queued searches do not spend provider quota', function () {
    $this->postJson('/api/v1/discover/jobs', ['query' => 'keyboard'])->assertAccepted();
    $this->travel(61)->minutes();

    Artisan::call('queue:work', ['connection' => 'discovery', '--queue' => 'discovery', '--once' => true, '--sleep' => 0]);

    $this->assertDatabaseCount('jobs', 0);
    Http::assertNothingSent();
});
