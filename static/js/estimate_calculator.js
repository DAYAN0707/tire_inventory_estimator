/**
 * 見積計算 ＆ 動的行追加スクリプト（完全プロフェッショナル仕様）
 * 全体の流れ：
 * 1章：データの準備と初期設定
 * 2章：タイヤ選択時のマスタデータ紐付け
 * 3章：金額計算ロジック（行単位 ＆ 諸費用API）
 * 4章：Django Formsetの整合性を保つ動的行追加
 * 5章：全体の集計 ＆ リアルタイム・バリデーション
 * 6章：ユーザー操作の監視（イベントリスナー）
 * 7章：タイヤ行削除（Formset対応）
 */

// 🔥 修正の本質：どの項目を手入力したかをキー単位（masterId_rowIndex）で記録する
let manualEditedKeys = new Set(); 
let chargeUpdateTimer; // Debounce（連打防止）用のタイマー
let logCounter = 0;    // 💥 修正②：console暴走対策用のログカウンター
let isInitialLoad = true; // 🚀 修正：初回ロード時のAPIループ防止フラグ

console.log("★★★ JSファイル読み込み成功！ ★★★");

$(function() {
    console.log("見積計算スクリプト始動");

    // ==========================================
    // --- 1章：初期化・マスタ読み込み ---
    // ==========================================
    // HTML内に埋め込まれたJSON（タイヤの単価や特価情報）を取得
    const tireMasterElement = document.getElementById('tire-master-data');
    const tireMasterData = JSON.parse(tireMasterElement?.textContent || "[]");

    // ==========================================
    // --- 2章：タイヤ金額計算（単価・小計） ---
    // ==========================================
    /**
     * タイヤ1行分の金額（単価・小計）を更新するメイン関数
     * 1. 選択されたタイヤを特定
     * 2. 特価適用の判定（4本単位 ＋ 端数分解ロジック）
     * 3. 画面表示の更新
     */
    function updateTireInfo($row) {
        // プルダウンから現在選択されているタイヤのIDを取得
        const tireId = $row.find('select[name$="-tire"]').val();
        // 入力されている数量を取得
        const qty = parseInt($row.find('input[name$="-quantity"]').val(), 10) || 0;
        
        // 🎯 マスタデータから該当するタイヤを探す
        const tire = tireMasterData.find(t => t.id == tireId);

        // 🎯 デバッグ用：マスタデータの中身をコンソールに表示して確認
        console.log("🔍 選択されたタイヤデータ:", tire);

        if (tire) {
            // --- 🎯 【修正】4本単位＋端数の分解計算ロジック ---
            const unitPrice = tire.unit_price || 0;
            const setPrice = tire.set_price || 0;

            // 👉 本数を「4本セット(setCount) ＋ 余り(remainder)」に分解
            const setCount = Math.floor(qty / 4);
            const remainder = qty % 4;

            // 🔥 小計の計算（セット特価分 ＋ 単品分）
            let subtotal = 0;
            if (setPrice > 0) {
                // 特価がある場合：(セット数 × 特価) + (余り × 通常単価)
                subtotal = (setPrice * setCount) + (unitPrice * remainder);
            } else {
                // 特価がない場合はすべて通常単価
                subtotal = unitPrice * qty;
            }

            // 🔍 デバッグ用：計算の内訳をログ出力
            console.log(`🧮 計算詳細: ${qty}本 = (${setCount}セット × ${setPrice}円) + (${remainder}本 × ${unitPrice}円)`);
            
            // --- 画面表示（UI）の更新 ---
            // 1. 通常単価の表示
            const $unitPriceCell = $row.find('.js-unit-price, .unit-price-display');
            $unitPriceCell.text(Number(unitPrice).toLocaleString() + "円");

            // 2. 4本特価の表示
            const $specialPriceCell = $row.find('.js-set-price, .special-price-display');
            $specialPriceCell.text(setPrice ? Number(setPrice).toLocaleString() + "円" : "---");
            
            // 3. 小計表示を更新
            const $subtotalCell = $row.find('.js-subtotal, .item-subtotal-display');
            $subtotalCell.text(subtotal.toLocaleString());
            
            // 🎯 【重要】✅ 修正①：計算結果をdata属性に保持（後で総合計の計算時に高速集計するため）
            $subtotalCell.data('value', subtotal);
            
            console.log(`✅ 行計算完了: ID=${tireId}, 数量=${qty}, 小計=${subtotal}`);
        } else {
            // タイヤが選択されていない、または削除された場合は表示をリセット
            $row.find('.js-unit-price, .unit-price-display, .js-set-price, .special-price-display, .js-subtotal, .item-subtotal-display').text("---");
            $row.find('.js-subtotal, .item-subtotal-display').data('value', 0);
        }
    }

    // ==========================================
    // --- 3章：諸費用計算ロジック（IDベース・安定版） ---
    // ==========================================
    let isUpdatingCharges = false; // 🔄 無限ループ防止用フラグ

    /**
     * 🔥 入力連打でAPIが火を吹かないよう制御（Debounce）
     * 数量を「4」に打ち込む際、「4」への変更1回だけを拾うように200ms待機する
     */
    function updateEstimateChargesDebounced() {
        clearTimeout(chargeUpdateTimer);
        chargeUpdateTimer = setTimeout(() => {
            updateEstimateCharges();
        }, 200); 
    }

    /**
     * 諸費用・工賃をAPI経由で更新する（セレクタ強化版）
     */
    function updateEstimateCharges() {
        // 🎯 修正：無限ループ防止
        if (isUpdatingCharges) return;
        isUpdatingCharges = true;

        const items = [];
        const chargeQtysForApi = {}; 

        // 💥 修正：API側でエラー表示を勝手に隠さない（表示管理は5章に一任）
        const $submitBtn = $('#submit-btn');               

        // 💥 問題③：購入区分の判定強化
        const purchaseVal = $('#id_purchase_type').val() || $('select[name="purchase_type"]').val() || "";
        const isExchange = String(purchaseVal).toLowerCase() === 'install' || purchaseVal == '1' || purchaseVal == 'exchange';
        
        if (logCounter % 20 === 0) console.log("🔍 purchaseVal 最終判定(isExchange):", isExchange);

        // 🎯 manualEditedKeys から現在の画面上の手動編集値を収集
        if (typeof manualEditedKeys !== 'undefined') {
            manualEditedKeys.forEach(key => {
                const $input = $(`input[name="charge_qtys[${key}]"]`);
                if ($input.length) chargeQtysForApi[key] = $input.val();
            });
        }
    
        $('.formset-row').not('.empty-form').each(function() {
            if ($(this).find('input[name$="-DELETE"]').prop('checked')) return; 

            const tireId = $(this).find('.js-tire-select').val();
            const qty = parseInt($(this).find('.js-quantity-input').val(), 10) || 0;

            // 💥 修正：API送信用データ（タイヤが選ばれていれば追加）
            if (tireId && tireId !== "") {
                items.push({ tire_id: tireId, quantity: qty });
            }
        });

        // 🎯 種類エラー判定（API計算前に即座に出す）
        if (isExchange && items.length > 2) {
            updateGrandTotalWithCharges(); 
            $('#js-charges-container').html('<tr><td colspan="4" class="text-center text-muted py-3">種類を減らしてください</td></tr>');
            isUpdatingCharges = false; 
            return;
        }

        if (items.length === 0) {
            console.log("⚠️ itemsが空です。計算をスキップします。");
            $('#js-charges-container').html('<tr><td colspan="4" class="text-center text-muted py-3">タイヤを選択すると工賃が自動計算されます</td></tr>');
            finalTotalUpdateOnly();
            isUpdatingCharges = false; 
            return; 
        }

        // 2. API呼び出し
        $.ajax({
            url: '/estimate/api/calculate-charges/', 
            method: 'POST',
            contentType: 'application/json',
            headers: { 'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').val() },
            data: JSON.stringify({ items: items, purchase_type: purchaseVal, charge_qtys: chargeQtysForApi }),
            success: function(response) {
                const $container = $('#js-charges-container');
                if ($container.length === 0) { isUpdatingCharges = false; return; }

                isUpdatingCharges = true;
                $container.empty();

                if (response.charges && response.charges.length > 0) {
                    let html = '';
                    response.charges.forEach(function(c) { 
                        const key = `${c.master_id}_${c.row_idx ?? 0}`;
                        const $existing = $(`input[name="charge_qtys[${key}]"]`);
                        let qty = (manualEditedKeys.has(key) && $existing.length) ? $existing.val() : Number(c.qty || 0);

                        const canEdit = c.is_editable; 
                        const readonlyAttr = canEdit ? "" : "readonly tabindex='-1' style='background-color: #f8f9fa; color: #6c757d; border: 1px solid #dee2e6; pointer-events: none;'";
                        const rowClass = (qty == 0) ? 'charge-row-zero text-muted opacity-50' : '';

                        html += `
                            <tr class="charge-row ${rowClass}">
                                <td class="align-middle">${c.name}</td>
                                <td class="text-end align-middle">${Number(c.price).toLocaleString()}円</td>
                                <td class="text-center align-middle">
                                    <input type="number" value="${qty}" name="charge_qtys[${key}]" 
                                        class="charge-qty-input form-control form-control-sm d-inline-block" 
                                        style="width: 70px;" min="0" data-price="${c.price}" ${readonlyAttr}>
                                    <input type="hidden" name="charge_master_ids[]" value="${c.master_id}">
                                </td>
                                <td class="text-end align-middle charge-subtotal-display">${(qty * c.price).toLocaleString()}円</td>
                            </tr>`;
                    });
                    $container.html(html);
                }
                finalTotalUpdateOnly(); 

                // 🔄 修正：AJAX終了後に確実にフラグを解除（setTimeout 0）
                setTimeout(() => { isUpdatingCharges = false; }, 0); 
            },
            error: function() { isUpdatingCharges = false; }
        }); 
    }

    // ==========================================
    // --- 4章：Django Formsetの整合性を保つ動的行追加 ---
    // ==========================================
    /**
     * 行追加ボタンの処理
     * 1. TOTAL_FORMSのカウントアップ
     * 2. テンプレート行の複製とID/Nameの置換
     */
    $('#add-row-btn').on('click', function(e) { 
        e.preventDefault(); 
        const $totalForms = $('#id_items-TOTAL_FORMS');
        const formCount = parseInt($totalForms.val());
        const $firstRow = $('.formset-row').first();
        const $newRow = $firstRow.clone(true); 

        $newRow.find('input, select').each(function() {
            const name = $(this).attr('name');
            const id = $(this).attr('id');
            if (name) $(this).attr('name', name.replace(/-\d+-/, `-${formCount}-`));
            if (id) $(this).attr('id', id.replace(/-\d+-/, `-${formCount}-`));
            $(this).val(""); 
        });
        $newRow.find('.js-unit-price, .js-subtotal, .unit-price-display, .special-price-display, .item-subtotal-display').text('---'); 
        $newRow.find('.item-subtotal-display').data('value', 0);
        
        $newRow.removeClass('deleted').show();
        $newRow.find('input[type="checkbox"][name$="-DELETE"]').prop('checked', false).val('');

        $('.formset-row').last().after($newRow);
        $totalForms.val(formCount + 1); 
        updateGrandTotalWithCharges();
    });

    // ==========================================
    // --- 5章：全体の集計 ＆ リアルタイム・バリデーション ---
    // ==========================================

    /**
     * ✅ 修正①：総合計のリアルタイム再計算（爆速 data属性集計版）
     */
    function finalTotalUpdateOnly() {
        let total = 0;
        $('.formset-row:visible').not('.empty-form').find('.js-subtotal, .item-subtotal-display').each(function() {
            total += Number($(this).data('value')) || 0;
        });
        $('.charge-row:visible').find('.charge-qty-input').each(function() {
            total += (Number($(this).val()) || 0) * (Number($(this).data('price')) || 0);
        });
        $('#js-grand-total').text(total.toLocaleString() + "円");
        
        if (logCounter++ % 20 === 0) {
            console.log("💰 リアルタイム総合計（data集計）:", total);
        }
    }

    /**
     * バリデーション結果の表示 ＆ 保存ボタンの制御
     */
    function updateGrandTotalDisplay(errorMsg) {
        let $msgArea = $('#validation-error-msg');
        
        // 🎯 修正：.table-responsiveを基準にエラーエリアを探す（HTMLにtire-tableクラスがなくても動く保険）
        if ($msgArea.length === 0) {
            $('.table-responsive').first().before('<div id="validation-error-msg" class="alert alert-danger" style="display:none; font-weight:bold;"></div>');
            $msgArea = $('#validation-error-msg');
        }

        finalTotalUpdateOnly(); 
        
        if (errorMsg) {
            console.log("🚨 エラー表示中:", errorMsg);
            $msgArea.text(errorMsg).show();
            $('button[type="submit"]').hide(); 
            return false;
        } else {
            $msgArea.hide();
            $('button[type="submit"]').show(); 
            return true;
        }
    }

    /**
     * 🎯 画面上の全数値を合算し、業務ルール（制限）をチェックする重要関数
     */
    function updateGrandTotalWithCharges() {
        let totalQty = 0;
        let tireTypes = new Set();
        const purchaseVal = $('#id_purchase_type').val() || $('select[name="purchase_type"]').val() || "";
        const isExchange = String(purchaseVal).toLowerCase() === 'install' || purchaseVal == '1' || purchaseVal == 'exchange';

        $('.formset-row:visible').not('.empty-form').each(function() {
            const qty = parseInt($(this).find('input[name$="-quantity"]').val(), 10) || 0;
            const tireId = $(this).find('select[name$="-tire"]').val();
            
            if (tireId && tireId !== "") {
                tireTypes.add(tireId);
                if (qty > 0) {
                    totalQty += qty;
                }
            }
        });

        // 🧪 デバッグログ
        console.log(`🧪 検証中... 種類数: ${tireTypes.size}, 合計本数: ${totalQty}`);

        let errorMsg = "";
        if (isExchange) {
            if (tireTypes.size > 2) {
                errorMsg = `【台数制限エラー】現在 ${tireTypes.size} 種類のタイヤが選択されています。交換作業ご希望の場合は、1台分(前後サイズ違いのお車など、最大2サイズ選択可能)までにしてください。`;
            }
            else if (totalQty > 8) {
                errorMsg = `【本数制限エラー】現在 ${totalQty} 本選択中です。交換作業ご希望の場合は、最大8本までにしてください。`;
            }
        }
        return updateGrandTotalDisplay(errorMsg);
    }
    
    // ===================================================
    // --- 6章：ユーザー操作の監視（イベントリスナー） ---
    // ===================================================
    $(document).ready(function() {
        console.log("🚀 見積計算JS: 初期化開始");
        
        updateGrandTotalWithCharges();
        
        if (isInitialLoad) {
            updateEstimateCharges();
            isInitialLoad = false;
        }

        $(document).on('change', 'select[name="purchase_type"], #id_purchase_type', function() {
            manualEditedKeys.clear(); 
            updateGrandTotalWithCharges();
            updateEstimateChargesDebounced();
        });
            
        $(document).on('change', '.js-tire-select, .js-quantity-input', function() {
            const $row = $(this).closest('tr');
            if ($row.hasClass('formset-row')) { updateTireInfo($row); }
            manualEditedKeys.clear(); 
            updateGrandTotalWithCharges();
            updateEstimateChargesDebounced();
        });

        $(document).on('input', '.charge-qty-input', function() {
            if (isUpdatingCharges) return;
            const name = $(this).attr('name');
            const keyMatch = name ? name.match(/\[(.*?)\]/) : null;
            if (keyMatch) manualEditedKeys.add(keyMatch[1]);

            const $row = $(this).closest('tr');
            const qty = parseFloat($(this).val()) || 0;
            const price = parseFloat($(this).data('price')) || 0;
            $row.find('.charge-subtotal-display').text((qty * price).toLocaleString() + "円");

            if (qty == 0) $row.addClass('charge-row-zero text-muted opacity-50');
            else $row.removeClass('charge-row-zero text-muted opacity-50');

            finalTotalUpdateOnly(); 
        });

        $('form').on('submit', function(e) {
            if (!updateGrandTotalWithCharges()) {
                e.preventDefault();
                alert("タイヤ構成にエラーがあるため、見積を確定できません。");
            }
        });
    });

    // ===================================================
    // --- 7章：タイヤ行削除（Django Formset 完全対応版）---
    // ===================================================
    $(document).on('click', '.delete-tire-row', function() {
        if ($('.formset-row:visible').length <= 1) { alert("最低1行は残してください。"); return; }
        const $row = $(this).closest('.formset-row');

        // ✅ 1. Djangoの削除フラグを立てる（最重要）
        const $deleteInput = $row.find('input[type="checkbox"][name$="-DELETE"]');
        if ($deleteInput.length) { $deleteInput.prop('checked', true).val('on'); }

        // ✅ 2. バリデーションエラーを回避し、数量を0に
        $row.find('input, select').each(function() {
            $(this).prop('required', false);
            if ($(this).attr('name')?.includes('-quantity')) {
                $(this).val(0); $(this).attr('min', 0);
            }
        });

        // ✅ 3. 見た目上の削除
        $row.addClass('deleted').hide(); 
        manualEditedKeys.clear(); 
        updateGrandTotalWithCharges(); 
        updateEstimateChargesDebounced(); 
        console.log("🗑 DELETEフラグを立て、行を削除しました");
    });
});