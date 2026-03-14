$(function() {
    console.log("見積計算スクリプト始動");

    // JSONデータの読み込み
    const tireMasterData = JSON.parse(document.getElementById('tire-master-data').textContent);

    /**
     * 1. 【タイヤ情報の反映】
     * 選択されたタイヤの単価や4本特価をJSONから取得し、行に保持・表示させる
     */
    function updateTireInfo($row) {
        const tireId = $row.find('select[name$="-tire"]').val();
        const tireData = tireMasterData.find(t => t.id == tireId);

        if (tireData) {
            // データ属性(price, set_price)として保持（unit_price, set_priceはDjango側の名前に合わせる）
            $row.data('unit-price', tireData.unit_price || 0);
            $row.data('set-price', tireData.set_price || 0);

            // 表示の更新
            $row.find('.js-unit-price').text(Number(tireData.unit_price).toLocaleString() + "円");
            $row.find('.js-set-price').text(Number(tireData.set_price).toLocaleString() + "円");
        }
        calculateRow($row);
    }

    /**
     * 2. 【行ごとの小計計算】
     * 4本特価を考慮した小計計算
     */
    function calculateRow($row) {
        const quantity = parseInt($row.find('input[name$="-quantity"]').val()) || 0;
        const normalPrice = parseFloat($row.data('unit-price')) || 0;
        const setPrice = parseFloat($row.data('set-price')) || 0;

        let subtotal = 0;
        if (setPrice > 0) {
            const sets = Math.floor(quantity / 4);
            const remainder = quantity % 4;
            subtotal = (sets * setPrice) + (remainder * normalPrice);
        } else {
            subtotal = quantity * normalPrice;
        }

        $row.find('.js-subtotal').text(subtotal.toLocaleString() + "円");
        // 全体の計算とバリデーションを実行
        updateGrandTotalWithCharges();
    }

    /**
     * 3. 【諸費用のAPI取得】
     */
    function updateEstimateCharges() {
        const purchaseType = $('select[name="purchase_type"]').val();
        const purchaseTypeText = $('select[name="purchase_type"] option:selected').text() || "";
        const $chargeSection = $('#charge-section');

        if (!purchaseTypeText.includes("交換")) {
            $chargeSection.hide();
            updateGrandTotalWithCharges();
            return;
        }

        $chargeSection.show();
        const items = [];
        $('.formset-row').not('.empty-form').each(function() {
            const tireId = $(this).find('select[name$="-tire"]').val();
            const quantity = parseInt($(this).find('input[name$="-quantity"]').val()) || 0;
            if (tireId && quantity > 0) {
                items.push({ tire_id: tireId, quantity: quantity });
            }
        });

        const $container = $('#charge-items-container');
        if (items.length === 0) {
            $container.html('<p class="text-muted">タイヤを選択すると表示されます</p>');
            return;
        }

        $.ajax({
            url: '/estimate/api/calculate-charges/',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ items: items, purchase_type: purchaseType }),
            headers: { 'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').val() },
            success: function(response) {
                $container.empty();
                if (response.charges && response.charges.length > 0) {
                    let html = '<table class="table table-sm"><thead><tr><th>項目</th><th>単価</th><th>数量</th><th>小計</th></tr></thead><tbody>';
                    response.charges.forEach((c) => {
                        html += `<tr>
                            <td>${c.name}</td>
                            <td>${c.price.toLocaleString()}円</td>
                            <td>
                                <input type="number" class="charge-qty-input form-control form-control-sm" style="width: 70px;" value="${c.qty}" data-price="${c.price}">
                            </td>
                            <td class="charge-subtotal-display">${c.subtotal.toLocaleString()}円</td>
                        </tr>`;
                    });
                    html += '</tbody></table>';
                    $container.html(html);
                }
                updateGrandTotalWithCharges(); 
            }
        });
    }

    /**
     * 4. 【リアルタイム・イベント監視】
     */
    $(document).on('change', 'select[name$="-tire"]', function() {
        updateTireInfo($(this).closest('tr'));
    });

    $(document).on('change', 'select[name="purchase_type"]', function() {
        updateEstimateCharges();
    });

    $(document).on('input', 'input[name$="-quantity"]', function() {
        calculateRow($(this).closest('tr'));
    });

    $(document).on('input', '.charge-qty-input', function() {
        const $input = $(this);
        const qty = parseFloat($input.val()) || 0;
        const price = parseFloat($input.data('price')) || 0;
        const subtotal = qty * price;
        $input.closest('tr').find('.charge-subtotal-display').text(subtotal.toLocaleString() + "円");
        updateGrandTotalWithCharges(); 
    });

    // 行追加
    $(document).on('click', '#add-row-btn', function(e) {
        e.preventDefault();
        const $tableBody = $('.formset-row').closest('tbody');
        const $firstRow = $tableBody.find('.formset-row').first();
        const $newRow = $firstRow.clone();
        $newRow.find('select').val('');
        $newRow.find('input').val('');
        $newRow.find('.js-unit-price, .js-set-price, .js-subtotal').text('0円');
        
        const totalForms = $('#id_items-TOTAL_FORMS');
        let count = parseInt(totalForms.val());
        $newRow.find('input, select').each(function() {
            const name = $(this).attr('name').replace(/-[0-9]+-/, `-${count}-`);
            $(this).attr('name', name).attr('id', `id_${name}`);
        });
        $tableBody.append($newRow);
        totalForms.val(count + 1);
    });

    // キー入力監視（バリデーション用）
    $(document).on("change keyup", "select, input", function() {
        updateGrandTotalWithCharges();
    });
});

/**
 * 5. 【総合計計算 ＆ バリデーション統合】
 * スコープ問題を解決するため、金額計算とエラーチェックを一つの流れで行います。
 */
function updateGrandTotalWithCharges() {
    // A. タイヤ明細の合計を計算
    let tireTotal = 0;
    let totalQty = 0;
    let tireTypes = new Set();

    $('.formset-row').not('.empty-form').each(function() {
        const subtotalText = $(this).find('.js-subtotal').text().replace(/[^\d]/g, '');
        tireTotal += parseFloat(subtotalText) || 0;

        const qty = parseInt($(this).find('input[name$="-quantity"]').val(), 10) || 0;
        const tireId = $(this).find('select[name$="-tire"]').val();

        if (tireId && tireId.trim() !== "" && qty > 0) {
            totalQty += qty;
            tireTypes.add(tireId);
        }
    });

    // B. 諸費用の合計を計算
    let chargeTotal = 0;
    $('.charge-subtotal-display').each(function() {
        const txt = $(this).text().replace(/[^\d]/g, '');
        chargeTotal += parseFloat(txt) || 0;
    });

    const finalTotal = tireTotal + chargeTotal;

    // C. バリデーション判定
    const purchaseTypeText = $('select[name="purchase_type"] option:selected').text() || "";
    let errorMsg = "";

    if (purchaseTypeText.includes("交換") && totalQty > 0) {
        const isOverQty = totalQty > 8;
        const isOverType = tireTypes.size > 2;

        if (isOverQty) {
            errorMsg = "【本数制限エラー】交換作業ありの場合、タイヤは8本までです。";
        } else if (isOverType) {
            errorMsg = "【台数制限エラー】作業予約は1台分（最大2サイズ可）までです。";
        }
    }

    // D. 表示への反映（すべての変数がここで出揃うので安全）
    updateGrandTotalDisplay(finalTotal, errorMsg);
}

/**
 * 6. 【画面表示とボタン制御】
 */
function updateGrandTotalDisplay(finalTotal, errorMsg) {
    const $msgArea = $('#validation-error-msg'); // 新設したメッセージエリア
    const $totalDisplay = $('#js-grand-total');  // 合計金額表示
    const $btn = $('button[type="submit"]');     // 保存ボタン

    // 金額の更新（エラーの有無に関わらず常に最新を表示）
    $totalDisplay.text(finalTotal.toLocaleString());

    if (errorMsg) {
        // エラーがある場合：赤背景のバッジで警告を表示し、保存ボタンを隠す
        $msgArea.text(errorMsg)
                .addClass('bg-danger')
                .removeClass('bg-info')
                .show();
        $btn.hide();
    } else {
        // 正常な時：メッセージを消し、ボタンを出す
        $msgArea.hide().text("");
        $btn.show();
    }
}