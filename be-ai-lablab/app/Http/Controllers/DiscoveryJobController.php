<?php

namespace App\Http\Controllers;

use App\Http\Requests\DiscoverProductsRequest;
use App\Jobs\DiscoverProducts;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Bus;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

class DiscoveryJobController extends Controller
{
    public function store(DiscoverProductsRequest $request): JsonResponse
    {
        $id = (string) Str::uuid();

        DB::transaction(function () use ($id, $request): void {
            Cache::store('database')->put('discovery:'.$id, ['status' => 'queued'], now()->addHour());
            Bus::dispatch(new DiscoverProducts($id, $request->validated()));
        });

        return response()->json(['id' => $id, 'status' => 'queued'], 202)
            ->header('Cache-Control', 'no-store, private');
    }

    public function show(string $id): JsonResponse
    {
        $result = Cache::store('database')->get('discovery:'.$id);
        abort_if($result === null, 404);

        return response()->json($result)->header('Cache-Control', 'no-store, private');
    }
}
