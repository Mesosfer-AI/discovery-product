<?php

use App\Http\Controllers\DiscoveryController;
use App\Http\Controllers\DiscoveryJobController;
use Illuminate\Support\Facades\Route;

Route::post('/v1/discover', DiscoveryController::class)->name('discovery.store');
Route::post('/v1/discover/jobs', [DiscoveryJobController::class, 'store'])->name('discovery.jobs.store');
Route::get('/v1/discover/jobs/{id}', [DiscoveryJobController::class, 'show'])->whereUuid('id')->name('discovery.jobs.show');
