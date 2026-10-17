<?php

use Illuminate\Http\Client\Request;
use Illuminate\Support\Facades\Http;

beforeEach(function () {
    config(['services.ai.url' => 'http://ai.internal:8000/', 'services.ai.timeout' => 180]);
    Http::preventStrayRequests();
});

test('discovery forwards validated shopping intent and returns the AI result', function () {
    $payload = [
        'query' => 'Sony WH-1000XM5',
        'budget_max' => 6000000,
        'currency' => 'IDR',
        'limit' => 3,
        'preferred_stores' => ['Erafone'],
        'country' => 'id',
    ];
    $result = [
        'query' => 'Sony WH-1000XM5',
        'total_discovered' => 30,
        'total_deduplicated' => 30,
        'total_verified' => 7,
        'execution_time_seconds' => 100.09,
        'provider_used' => 'amd',
        'recommendations' => [[
            'rank' => 1,
            'product' => [
                'id' => 'sony-1', 'title' => 'Sony WH-1000XM5', 'price' => 4099000,
                'currency' => 'IDR', 'url' => 'https://example.com/products/sony-1',
                'image_url' => null, 'store_name' => 'Erafone', 'rating' => 4.4,
                'review_count' => 50, 'description' => 'Wireless headphones', 'source' => 'web',
            ],
            'trust_score' => 80, 'match_score' => 90,
            'why_recommended' => 'Within budget with an official warranty.',
            'pros' => ['Official warranty'], 'cons' => ['Higher price'],
        ]],
    ];
    Http::fake(['ai.internal:8000/api/v1/discover' => Http::response($result)]);

    $this->postJson('/api/v1/discover', [
        ...$payload, 'country' => ' ID ', 'ai_service_url' => 'https://untrusted.example',
    ])->assertOk()->assertExactJson($result);

    Http::assertSent(fn (Request $request) => $request->method() === 'POST'
        && $request->url() === 'http://ai.internal:8000/api/v1/discover'
        && $request->data() == $payload);
    Http::assertSentCount(1);
});

test('discovery allows AI defaults and an empty recommendation list', function () {
    $result = [
        'query' => 'keyboard', 'total_discovered' => 0, 'total_deduplicated' => 0,
        'total_verified' => 0, 'recommendations' => [],
        'execution_time_seconds' => 0.1, 'provider_used' => 'amd',
    ];
    Http::fake(['ai.internal:8000/api/v1/discover' => Http::response($result)]);

    $this->postJson('/api/v1/discover', ['query' => 'keyboard'])
        ->assertOk()->assertExactJson($result);

    Http::assertSent(fn (Request $request) => $request->data() === ['query' => 'keyboard']);
});

test('discovery gives PHP enough execution time to handle the AI timeout', function () {
    $previousLimit = (int) ini_get('max_execution_time');
    set_time_limit(30);
    Http::fake(['ai.internal:8000/api/v1/discover' => Http::response(['recommendations' => []])]);

    try {
        $this->postJson('/api/v1/discover', ['query' => 'keyboard'])->assertOk();

        expect((int) ini_get('max_execution_time'))->toBeGreaterThan(180);
    } finally {
        set_time_limit($previousLimit);
    }
});

test('discovery rejects invalid input before contacting AI', function (array $input, string $field) {
    $this->postJson('/api/v1/discover', $input)
        ->assertUnprocessable()->assertJsonValidationErrors($field);

    Http::assertNothingSent();
})->with([
    'missing query' => [[], 'query'],
    'short query' => [['query' => 'a'], 'query'],
    'blank query' => [['query' => '  '], 'query'],
    'negative budget' => [['query' => 'keyboard', 'budget_max' => -1], 'budget_max'],
    'zero limit' => [['query' => 'keyboard', 'limit' => 0], 'limit'],
    'excess limit' => [['query' => 'keyboard', 'limit' => 11], 'limit'],
    'invalid country' => [['query' => 'keyboard', 'country' => 'IDN'], 'country'],
    'invalid currency' => [['query' => 'keyboard', 'currency' => 'IDRX'], 'currency'],
    'invalid stores' => [['query' => 'keyboard', 'preferred_stores' => 'Erafone'], 'preferred_stores'],
    'stores object instead of list' => [['query' => 'keyboard', 'preferred_stores' => ['store' => 'Erafone']], 'preferred_stores'],
    'invalid store entry' => [['query' => 'keyboard', 'preferred_stores' => [123]], 'preferred_stores.0'],
]);

test('discovery hides upstream error details', function (int $status) {
    Http::fake(['ai.internal:8000/api/v1/discover' => Http::response([
        'detail' => 'Internal provider URL and credentials must not reach the frontend.',
    ], $status)]);

    $this->postJson('/api/v1/discover', ['query' => 'keyboard'])
        ->assertStatus(502)->assertExactJson(['message' => 'AI discovery failed. Please try again later.']);

    Http::assertSentCount(1);
})->with([422, 500]);

test('discovery preserves search rate limits without exposing upstream details', function () {
    Http::fake(['ai.internal:8000/api/v1/discover' => Http::response(['detail' => 'Private provider details'], 429)]);

    $this->postJson('/api/v1/discover', ['query' => 'sepatu roda'])
        ->assertStatus(429)
        ->assertExactJson(['message' => 'Search is temporarily blocked. Please try again later.']);
});

test('discovery returns a service error when AI cannot be reached', function () {
    Http::fake(['ai.internal:8000/api/v1/discover' => Http::failedConnection()]);

    $this->postJson('/api/v1/discover', ['query' => 'keyboard'])
        ->assertServiceUnavailable()
        ->assertExactJson(['message' => 'AI discovery is unavailable. Please try again later.']);
});

test('discovery rejects malformed upstream responses', function (mixed $body) {
    Http::fake(['ai.internal:8000/api/v1/discover' => Http::response($body)]);

    $this->postJson('/api/v1/discover', ['query' => 'keyboard'])
        ->assertStatus(502)->assertExactJson(['message' => 'AI discovery returned an invalid response.']);
})->with([
    'html' => ['<html>Gateway error</html>'],
    'missing recommendations' => [['message' => 'unexpected payload']],
    'invalid recommendations' => [['recommendations' => 'not a list']],
    'object instead of list' => [['recommendations' => ['product' => 'not a list']]],
]);
