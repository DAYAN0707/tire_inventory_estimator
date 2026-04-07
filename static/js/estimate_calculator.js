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


    let logCounter = 0; // デバッグログ用

    // ==========================================
    // --- 1章：初期化・マスタ読み込み ---
    // ==========================================
    /**
     * 【処理の目的】
     * DjangoのViewから渡された「タイヤ全件の価格表（マスタデータ）」をJavaScriptで扱えるようにする
     * これにより、サーバーと通信せずに画面上で瞬時に単価や特価を引き出すことが可能
     */
    // HTML内に埋め込まれたJSON（タイヤの単価や特価情報）を取得
    const tireMasterElement = document.getElementById('tire-master-data');
    
    // マスタデータが存在しない場合は空配列として初期化（エラー防止）
    const tireMasterData = JSON.parse(tireMasterElement?.textContent || "[]");

    // 🔍 デバッグ用：マスタデータが正しくロードされたか確認（空ならView側の設定ミス）
    console.log("🛞 tireMasterDataのロード状況:", tireMasterData);

    // ==========================================
    // --- 2章：タイヤ金額計算（単価・小計）＆ フォーム操作 ---
    // ==========================================
    /**
     * タイヤ1行分の金額（単価・小計）を更新するメイン関数
     * 1. 選択されたタイヤを特定（マスタデータからの逆引き）
     * 2. 特価適用の判定（4本単位 ＋ 端数分解ロジック）
     * 3. 画面表示（UI）のリアルタイム更新
     */
    function updateTireInfo($row) {
        // 🔥 重要：どの行を操作しているかインデックスをログ出力
        const rowIndex = $row.index();
        
        // プルダウンから現在選択されているタイヤのIDを取得
        const tireId = $row.find('select[name$="-tire"]').val();
        
        // 入力されている数量を取得（10進数で数値化、空なら0）
        const qty = parseInt($row.find('input[name$="-quantity"]').val(), 10) || 0;
        
        // 🎯 マスタデータから該当するタイヤを探す
        const tire = tireMasterData.find(t => String(t.id) === String(tireId));

        // 🎯 デバッグ用：見つかったタイヤの情報をコンソールに表示
        console.log(`🔍 行[${rowIndex}] 検索実行: tireId=${tireId} -> 結果:`, tire);

        if (tire) {
            // --- 🎯 4本単位＋端数の分解計算ロジック ---
            const unitPrice = parseFloat(tire.unit_price) || 0;
            const setPrice = parseFloat(tire.set_price) || 0;

            // 👉 本数を「4本セット(setCount) ＋ 余り(remainder)」に分解
            const setCount = Math.floor(qty / 4);
            const remainder = qty % 4;

            // 🔥 小計の計算（セット特価分 ＋ 単品分）
            let subtotal = 0;
            if (setPrice > 0 && setCount > 0) {
                subtotal = (setPrice * setCount) + (unitPrice * remainder);
            } else {
                subtotal = unitPrice * qty;
            }

            // 🔍 デバッグ用：計算の内訳をログ出力
            console.log(`🧮 行[${rowIndex}] 計算詳細: ${qty}本 = (${setCount}セット × ${setPrice}円) + (${remainder}本 × ${unitPrice}円)`);
            
            // --- 画面表示（UI）の更新 ---
            const $unitPriceCell = $row.find('.js-unit-price, .unit-price-display');
            $unitPriceCell.text(Number(unitPrice).toLocaleString() + "円");

            const $specialPriceCell = $row.find('.js-set-price, .special-price-display');
            $specialPriceCell.text(setPrice > 0 ? Number(setPrice).toLocaleString() + "円" : "---");
            
            const $subtotalCell = $row.find('.js-subtotal, .item-subtotal-display');
            $subtotalCell.text(subtotal.toLocaleString());
            
            // 🎯 計算結果をdata属性に保持
            $subtotalCell.data('value', subtotal);
            
            console.log(`✅ 行[${rowIndex}] 計算完了: ID=${tireId}, 数量=${qty}, 小計=${subtotal}`);
        } else {
            // リセット処理
            $row.find('.js-unit-price, .unit-price-display, .js-set-price, .special-price-display, .js-subtotal, .item-subtotal-display').text("---");
            $row.find('.js-subtotal, .item-subtotal-display').data('value', 0);
            
            if (tireId) {
                console.warn(`⚠️ 注意: 行[${rowIndex}] のID(${tireId})がマスタに見つかりません。`);
            }
        }
    }

    /**
     * フォームセットの動的追加（独立設計版）
     * clone(false) を使用し、1行目のイベントを引き継がないように制御
     */
    $('#add-form').click(function(e) {
        e.preventDefault();
        const $firstRow = $('.formset-row').first();
        // 🎯 clone(false) で、1行目に紐付いた古い検索イベント等をコピーしない
        const $newRow = $firstRow.clone(false);

        const $totalForms = $('#id_items-TOTAL_FORMS');
        const count = parseInt($totalForms.val());

        // IDとNameの置換（Django Formsetの標準ルール）
        $newRow.find('input, select, span, div').each(function() {
            const id = $(this).attr('id');
            if (id) $(this).attr('id', id.replace(/-0-/, `-${count}-`));
            
            const name = $(this).attr('name');
            if (name) $(this).attr('name', name.replace(/-0-/, `-${count}-`));
        });

        // 🎯 コピーされた値をクリア
        $newRow.find('select').val('');
        $newRow.find('input[type="number"]').val(0);
        $newRow.find('input[type="text"]').val('');
        $newRow.find('.js-unit-price, .unit-price-display, .js-set-price, .special-price-display, .js-subtotal, .item-subtotal-display').text("---");
        $newRow.find('.js-subtotal, .item-subtotal-display').data('value', 0);

        // 画面に追加
        $newRow.hide().appendTo('#formset-container').fadeIn(300);
        $totalForms.val(count + 1);
        
        console.log(`➕ 行を追加しました。現在の合計行数: ${count + 1}`);
    });

    /**
     * 🎯 タイヤ検索ボタンのイベント（イベント委譲）
     * $(document).on を使うことで、後から追加された行にも自動対応
     */
    $(document).on('click', '.search-btn', function() {
        // 🔥 クリックされたボタンから「自分の行」を特定
        const $row = $(this).closest('.formset-row');
        const rowIndex = $row.index();
        
        const manufacturer = $row.find('.search-manufacturer').val();
        const size = $row.find('.search-size').val();

        console.log(`🔍 検索ボタン押下 - 行[${rowIndex}]: メーカー=${manufacturer}, サイズ=${size}`);

        if (!manufacturer || !size) {
            alert("メーカーとサイズを選択してください");
            return;
        }

        // Ajaxでタイヤ検索実行
        $.ajax({
            url: '/estimate/api/search-tires/',
            method: 'GET',
            data: { manufacturer: manufacturer, size: size },
            success: function(data) {
                const $select = $row.find('select[name$="-tire"]');
                $select.empty().append('<option value="">選択してください</option>');
                if (data.length > 0) {
                    data.forEach(tire => {
                        const priceLabel = tire.price ? ` (￥${tire.price.toLocaleString()})` : '';
                        $select.append(`<option value="${tire.id}">${tire.name}${priceLabel}</option>`);
                    });
                    console.log(`✅ 行[${rowIndex}]: ${data.length}件の検索結果を表示`);
                } else {
                    alert("該当するタイヤが見つかりませんでした");
                }
            },
            error: function() {
                console.error(`❌ 行[${rowIndex}]: 検索API通信エラー`);
                alert("検索中にエラーが発生しました");
            }
        });
    });

    // =================================================
    // --- 3章：諸費用計算ロジック（IDベース・安定版） ---
    // =================================================
    let isUpdatingCharges = false; // 🔄 無限ループ防止用フラグ
    let chargeUpdateTimer;         // Debounce用タイマー

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
     * 諸費用・工賃をAPI経由で更新し、ランフラット加算を自動連動させる
     * 1. 選択されたタイヤと購入区分をAPIに送信
     * 2. 返ってきた諸費用データ（JSON）を元にHTMLを生成
     * 3. 【重要】交換工賃の本数を集計し、ランフラット行に強制連動
     */
    function updateEstimateCharges() {
        // 🎯 無限ループ防止
        if (isUpdatingCharges) return;
        isUpdatingCharges = true;

        const items = [];
        const chargeQtysForApi = {}; 

        // 💥 購入区分の判定（IDとname両方から探し、文字列・数値どちらでも判定できるように）
        const purchaseVal = $('#id_purchase_type').val() || $('select[name="purchase_type"]').val() || "";
        const isExchange = String(purchaseVal).toLowerCase() === 'install' || purchaseVal == '1' || purchaseVal == 'exchange';
        
        // 🎯 手動編集された諸費用（手入力値）を収集
        if (typeof manualEditedKeys !== 'undefined') {
            manualEditedKeys.forEach(key => {
                const $input = $(`input[name="charge_qtys[${key}]"]`);
                if ($input.length) chargeQtysForApi[key] = $input.val();
            });
        }
    
        // 🎯 Django Formsetから有効なタイヤデータを抽出
        $('.formset-row').not('.empty-form').each(function() {
            if ($(this).find('input[name$="-DELETE"]').prop('checked')) return; 

            const tireId = $(this).find('select[name$="-tire"]').val();
            const qty = parseInt($(this).find('input[name$="-quantity"]').val(), 10) || 0;

            if (tireId && tireId !== "" && qty > 0) {
                items.push({ tire_id: tireId, quantity: qty });
            }
        });

        // 🎯 バリデーション：交換作業時は2種類まで
        if (isExchange && items.length > 2) {
            $('#js-charges-container').html('<tr><td colspan="4" class="text-center text-muted py-3">種類を減らしてください</td></tr>');
            if (typeof updateGrandTotalWithCharges === "function") updateGrandTotalWithCharges(); 
            isUpdatingCharges = false; 
            return;
        }

        // 🎯 バリデーション：タイヤ未選択時
        if (items.length === 0) {
            $('#js-charges-container').html('<tr><td colspan="4" class="text-center text-muted py-3">タイヤを選択すると工賃が自動計算されます</td></tr>');
            if (typeof finalTotalUpdateOnly === "function") finalTotalUpdateOnly();
            isUpdatingCharges = false; 
            return; 
        }

        // 🚀 API通信開始
        $.ajax({
            url: '/estimate/api/calculate-charges/', 
            method: 'POST',
            contentType: 'application/json',
            headers: { 'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').val() || getCookie('csrftoken') },
            data: JSON.stringify({ 
                items: items, 
                purchase_type: purchaseVal, 
                charge_qtys: chargeQtysForApi 
            }),
            success: function(response) {
                const $container = $('#js-charges-container');
                if ($container.length === 0) return;

                $container.empty();

                if (response.charges && response.charges.length > 0) {
                    
                    // =============================================================
                    // 🎯 【連動の要】工賃本数の事前集計 & ランフラット判定
                    // =============================================================
                    let totalLaborQty = 0;
                    response.charges.forEach(c => {
                        // "工賃" という文字が含まれる項目の数量を足す
                        if (c.name.includes("工賃")) {
                            totalLaborQty += Number(c.qty || 0);
                        }
                    });
                    console.log("🛠️ 工賃合計（事前集計）:", totalLaborQty);

                    let hasRunflat = false;
                    $('.formset-row').not('.empty-form').each(function() {
                        if ($(this).find('input[name$="-DELETE"]').prop('checked')) return;
                        const tId = $(this).find('select[name$="-tire"]').val();
                        const tire = tireMasterData.find(t => String(t.id) === String(tId));
                        // デバッグ用
                        console.log("🛞 タイヤ確認:", tire);
                        if (tire && (tire.is_runflat === true || tire.is_runflat == 1)) {
                            hasRunflat = true;
                        }
                    });
                    console.log("🛞 ランフラット判定:", hasRunflat);

                    // =============================================================
                    // 🎯 描画ループ（ここでランフラット数量を強制上書き）
                    // =============================================================
                    let html = '';
                    response.charges.forEach(function(c) { 
                        const key = `${c.master_id}_${c.row_idx ?? 0}`;
                        const $existing = $(`input[name="charge_qtys[${key}]"]`);
                        
                        let qty = Number(c.qty || 0);
                        
                        // 🔥 ランフラット行の場合、上で集計した工賃合計を強制適用
                        if (c.name.includes("ランフラット")) {
                            qty = (isExchange && hasRunflat) ? totalLaborQty : 0;
                            console.log("🎯 ランフラット行に数量を適用:", qty);
                        }
                        // 手動編集されている場合は、手動の値を優先（ランフラット以外）
                        else if (typeof manualEditedKeys !== 'undefined' && manualEditedKeys.has(key) && $existing.length) {
                            qty = $existing.val();
                        }

                        const canEdit = c.is_editable; 
                        const readonlyAttr = canEdit ? "" : "readonly tabindex='-1' style='background-color: #f8f9fa; color: #6c757d; border: 1px solid #dee2e6; pointer-events: none;'";
                        const rowClass = (qty == 0) ? 'charge-row-zero text-muted opacity-50' : '';

                        html += `
                            <tr class="charge-row ${rowClass}">
                                <td class="align-middle">${c.name}</td>
                                <td class="text-end align-middle">${Number(c.price).toLocaleString()}円</td>
                                <td class="text-center align-middle">
                                    <input type="number" 
                                        value="${qty}" 
                                        name="charge_qtys[${key}]" 
                                        class="charge-qty-input form-control form-control-sm d-inline-block" 
                                        style="width: 70px;" 
                                        min="0" 
                                        data-price="${c.price}" 
                                        ${readonlyAttr}>
                                    <input type="hidden" name="charge_master_ids[]" value="${c.master_id}">
                                </td>
                                <td class="text-end align-middle charge-subtotal-display">
                                    ${(qty * c.price).toLocaleString()}円
                                </td>
                            </tr>`;
                    });
                    $container.html(html);
                }

                if (typeof finalTotalUpdateOnly === "function") finalTotalUpdateOnly(); 

                // 🔄 AJAX終了後にフラグ解除
                setTimeout(() => { isUpdatingCharges = false; }, 0); 
            },
            error: function(xhr) {
                console.error("❌ API計算エラー:", xhr.responseText);
                isUpdatingCharges = false;
            }
        }); 
    }

    // =================================================
    // --- 4章：Django Formsetの整合性を保つ動的行追加 ---
    // =================================================
    /**
     * 行追加ボタンの処理
     * 1. TOTAL_FORMSのカウントアップ
     * 2. テンプレート行の複製とID/Nameの置換
     */
    $('#add-row-btn').on('click', function(e) { 
        e.preventDefault(); 
        // 🎯 Django Formsetの管理用TOTAL_FORMSを正確に更新するため、現在の行数を取得
        const $totalForms = $('#id_items-TOTAL_FORMS');
        // 🎯 既存の行数を元に新しい行のIDとNameを置換していく（これがFormsetの整合性を保つ鍵）
        const formCount = parseInt($totalForms.val());
        // 🎯 最初の行を複製して新しい行を作る（これでHTML構造もクラスもそのままコピーされる）
        const $firstRow = $('.formset-row').first();
        // 🎯 ここで複製する行を指定。通常は最初の行を複製するが、もし最後の行が空ならそれを複製しても良い（ユーザーが最後の行を編集している可能性があるため）
        const $newRow = $firstRow.clone(true); 

        // 🎯 複製した行の中のinputやselectのnameとidを新しい行数に置換していく（これがFormsetの整合性を保つ鍵）
        $newRow.find('input, select').each(function() {
            // 🎯 まずはname属性を取得（これがFormsetの管理に必要）
            const name = $(this).attr('name');
            // 🎯 name属性がある場合は、-0-の部分を新しい行数に置換する（これでDjango Formsetが正しく認識できるようになる）
            const id = $(this).attr('id');
            if (name) $(this).attr('name', name.replace(/-\d+-/, `-${formCount}-`));
            if (id) $(this).attr('id', id.replace(/-\d+-/, `-${formCount}-`));
            $(this).val(""); 
        });
        // 🎯 複製した行の金額表示部分をリセット（新しい行は空なので金額もリセットしておく）
        $newRow.find('.js-unit-price, .js-subtotal, .unit-price-display, .special-price-display, .item-subtotal-display').text('---'); 
        $newRow.find('.item-subtotal-display').data('value', 0);

        // 🎯 複製した行の削除フラグをリセット（新しい行は削除されていない状態にしておく）
        $newRow.removeClass('deleted').show();
        $newRow.find('input[type="checkbox"][name$="-DELETE"]').prop('checked', false).val('');

        // 🎯 複製した行をフォームセットの最後に追加（これでユーザーが新しい行をすぐに編集できる）
        $('.formset-row').last().after($newRow);
        $totalForms.val(formCount + 1); 
        updateGrandTotalWithCharges();
    });

    // ===================================================
    // --- 5章：全体の集計 ＆ リアルタイム・バリデーション ---
    // ===================================================

    /**
     * ✅ 総合計のリアルタイム再計算（爆速 data属性集計版）
     * 総合計はdata属性の値を集計する方式。DOMを直接読み取るよりも高速で、複雑な計算ロジックも速く処理できる
     */
    //
    function finalTotalUpdateOnly() {
        let total = 0;
        // 🎯小計はdata属性から集計（これが速いポイント）
        $('.formset-row:visible').not('.empty-form').find('.js-subtotal, .item-subtotal-display').each(function() {
            total += Number($(this).data('value')) || 0;
        });
        // 🎯諸費用も工賃も同じ
        $('.charge-row:visible').find('.charge-qty-input').each(function() {
            total += (Number($(this).val()) || 0) * (Number($(this).data('price')) || 0);
        });
        // 最終合計を画面に表示
        $('#js-grand-total').text(total.toLocaleString() + "円");
        
        // console用のログカウンター使用により、総合計ログが暴走しないよう制御（20回に1回のみ表示）
        if (logCounter++ % 20 === 0) {
            console.log("💰 リアルタイム総合計（data集計）:", total);
        }
    }

    /**
     * バリデーション結果の表示 ＆ 保存ボタンの制御
     */
    function updateGrandTotalDisplay(errorMsg) {
        let $msgArea = $('#validation-error-msg');
        
        // 🎯.table-responsiveを基準にエラーエリアを探す（HTMLにtire-tableクラスがなくても動く保険）
        if ($msgArea.length === 0) {
            // もしエリアがなければ、.table-responsiveの前にエリアを作る（これでHTML構造に依存せずにエラー表示ができるようになる）
            $('.table-responsive').first().before('<div id="validation-error-msg" class="alert alert-danger" style="display:none; font-weight:bold;"></div>');
            $msgArea = $('#validation-error-msg');
        }
        finalTotalUpdateOnly(); 

        //エラーがある場合はエラーメッセージを表示して保存ボタンは隠す。エラーがなければ保存ボタンを表示してエラーメッセージは隠す
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
        //タイヤの種類と合計本数をカウントするロジック
        let totalQty = 0;
        let tireTypes = new Set();
        // 購入区分の判定強化（これでIDベースでもnameベースでも正しく判定できるようになる）
        const purchaseVal = $('#id_purchase_type').val() || $('select[name="purchase_type"]').val() || "";
        // 🔥 交換作業かどうかの判定を強化（これで「install」「1」「exchange」のいずれかであれば交換作業とみなすようになる）
        const isExchange = String(purchaseVal).toLowerCase() === 'install' || purchaseVal == '1' || purchaseVal == 'exchange';

        // 🎯 タイヤの種類と数量を数えるロジック（これが業務ルールのチェックに必要）
        $('.formset-row:visible').not('.empty-form').each(function() {
            // 🚀 クラスベースから name属性ベースへ変更（これでHTML構造に依存せずに確実に値を拾えるようになる）
            const qty = parseInt($(this).find('input[name$="-quantity"]').val(), 10) || 0;
            // 🎯 タイヤIDの取得も同様
            const tireId = $(this).find('select[name$="-tire"]').val();
            
            // 🧪 デバッグログを追加（これで見える化！）
            if (tireId && tireId !== "") {
                tireTypes.add(tireId);
                if (qty > 0) {
                    totalQty += qty;
                }
            }
        });

        // 🎯 デバッグ用：タイヤの種類数と合計本数をログに出す（これで業務ルールのチェックが正しく行われているかを確認できる）
        console.log(`🧪 検証中... 種類数: ${tireTypes.size}, 合計本数: ${totalQty}`);

        let errorMsg = "";
        // 🔥 交換作業の場合の業務ルールチェック（種類数と本数の制限）
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

    // ===============================================================
    // --- 6章：ユーザー操作の監視（イベントリスナー） & 初期状態の復元 ---
    // ===============================================================
    /**
     * 【この章の役割】
     * 1. 在庫一覧から「見積に追加」して遷移してきた際のデータ復元
     * 2. ユーザーがタイヤ、本数、購入区分を変更した際のリアルタイム計算
     * 3. 諸費用・工賃を手動で微調整した際の合計金額への即時反映
     */

    /**
     * 🚀 実行順序制御フラグ: isRestoring
     * 目的: ページ読み込み直後の「復元処理」の最中に、空のデータでAPI計算が走るのを防ぐ
     * 仕組み: 復元がすべて完了するまで true にしておき、各計算関数の入り口でガードをかける
     */
    let isRestoring = true;

    $(document).ready(function() {
        console.log("🚀 見積計算JS: 初期化開始 (isRestoring: true)");

        // ==========================================================================
        // --- 🎯 1. DB/在庫一覧からの状態復元（add-itemからの戻り対応） ---
        // ==========================================================================
        /**
         * テンプレート(estimate_create.html)内の <script id="estimate-data"> から
         * Python側で用意したJSONデータを読み取り、フォームに流し込む
         */
        const estimateDataElement = document.getElementById('estimate-data');
        let estimateData = { items: [] };

        if (estimateDataElement) {
            // textContentからJSONを取得し、前後の不要な空白や改行を掃除
            const rawContent = estimateDataElement.textContent.trim();

            if (rawContent) {
                try {
                    // JSON文字列をJavaScriptオブジェクトに変換
                    estimateData = JSON.parse(rawContent);

                    // 復元すべきデータ（タイヤ選択情報）がある場合のみ実行
                    if (estimateData.items && estimateData.items.length > 0) {
                        console.log("📦 在庫からの選択データを検知。復元プロセスを開始します...");

                        const requiredRows = estimateData.items.length; // 必要な行数
                        let $currentRows = $('#tire-formset-body tr.formset-row'); // 現在のHTML上の行

                        // --- 手順A：Django Formsetの行数を確保 ---
                        /**
                         * 直接HTMLをいじるのではなく、既存の「行追加ボタン」を擬似的にクリックする
                         * これにより、Djangoの管理用フィールド(ManagementForm)の 
                         * TOTAL_FORMS カウントが正しく加算され、保存時の不整合を防げる
                         */
                        while ($currentRows.length < requiredRows) {
                            console.log(`➕ 行不足を確認（現在:${$currentRows.length}/必要:${requiredRows}）。自動追加を実行。`);
                            $('#add-row-btn').click();
                            // 追加後の最新の行リストを再取得してループ判定に使う
                            $currentRows = $('#tire-formset-body tr.formset-row');
                        }

                        // --- 手順B：各入力フィールドへのデータ流し込み ---
                        estimateData.items.forEach((item, index) => {
                            const $targetRow = $currentRows.eq(index);

                            if ($targetRow.length > 0) {
                                console.log(`🔧 行[${index}] 復元中: タイヤID[${item.tire_id}], 数量[${item.quantity}]`);

                                /**
                                 * セレクタのポイント:
                                 * Django Formsetは name="items-0-tire" のように動的なIDを振るため、
                                 * [name$="-tire"]（-tireで終わるもの）という後方一致セレクタで確実に捕まえる
                                 */
                                $targetRow.find('select[name$="-tire"]').val(item.tire_id);
                                $targetRow.find('input[name$="-quantity"]').val(item.quantity);

                                /**
                                 * 🎯 手動でのイベント発火:
                                 * jQueryの .val() で値を書き換えても、ブラウザの 'change' イベントは自動では起きない
                                 * そのため、単価の取得やインチの判別を行う updateTireInfo を手動で呼び出す必要がある
                                 * (※この時点ではまだ isRestoring=true なので、重いAPI通信はスキップされる)
                                 */
                                updateTireInfo($targetRow);
                            }
                        });

                        // --- 手順C：復元の仕上げ（一括計算の許可） ---
                        console.log("🔄 復元データの流し込み完了。初回一括計算を許可します。");
                        
                        // 💡 ここでフラグを解除することで、ガードがかかっていた計算関数たちが動けるようになる
                        isRestoring = false; 

                        // データがすべて入った「完成状態」で初めて、全体合計と工賃APIを叩く
                        updateGrandTotalWithCharges();
                        updateEstimateCharges();

                        console.log("✅ 復元および初期計算が正常に終了しました。");
                    } else {
                        isRestoring = false; // アイテムが空の場合は即座に通常モードへ
                    }
                } catch (e) {
                    console.error("❌ 復元データの解析に失敗しました:", e, "対象内容:", rawContent);
                    isRestoring = false; // エラーが起きてもユーザーが操作できるようにフラグは折る
                }
            } else {
                isRestoring = false; // データ自体が空文字の場合
            }
        } else {
            isRestoring = false; // 要素が存在しない（新規作成時など）場合
        }

        // ==========================================================================
        // --- 🎯 2. リアルタイム監視（ユーザー操作への連動） ---
        // ==========================================================================

        /**
         * 【購入区分の変更監視】
         * 「持ち帰り」か「交換作業」かで工賃の計算ロジックが大きく変わるため
         * 購入区分の変更をしっかりキャッチして、工賃の再計算を走らせる必要がある
         */
        $(document).on('change', 'select[name="purchase_type"], #id_purchase_type', function() {
            if (isRestoring) return; // 復元中の余計な発火をガード
            console.log("🔄 購入区分が変更されました。諸費用を再スキャンします。");
            
            // ユーザーが手動でいじった工賃の記憶を一度消し、自動計算を優先させる
            manualEditedKeys.clear(); 
            updateGrandTotalWithCharges();
            updateEstimateChargesDebounced(); // 負荷軽減のためデバウンス版（遅延実行）を呼ぶ
        });

        /**
         * 【タイヤ種別・数量の変更監視】
         * タイヤの種類が変われば「セット価格」や「廃タイヤ処分料」の対象が変わるため
         */
        $(document).on('change', 'select[name$="-tire"], input[name$="-quantity"]', function() {
            if (isRestoring) return; // 復元中の余計な発火をガード

            const $row = $(this).closest('tr');
            if ($row.hasClass('formset-row')) {
                // その行の単価・インチ・小計を再計算
                updateTireInfo($row);
            }
            
            // 構成が変わったので工賃も自動計算をやり直す
            manualEditedKeys.clear();
            updateGrandTotalWithCharges();
            updateEstimateChargesDebounced();
        });

        /**
         * 【工賃・諸費用の数量（手入力）の監視】
         * 自動計算された工賃をユーザーが現場判断で書き換えた場合への対応
         */
        $(document).on('input', '.charge-qty-input', function() {
            // 無限ループ防止（APIによる自動更新中は何もしない）
            if (isRestoring || (typeof isUpdatingCharges !== 'undefined' && isUpdatingCharges)) return;

            /**
             * 手動修正の記録:
             * name属性から「masterId_rowIndex」形式のキーを抜き出し、
             * 以降の自動計算APIの結果で上書きされないように保護リスト(manualEditedKeys)へ入れる
             */
            const name = $(this).attr('name');
            const keyMatch = name ? name.match(/\[(.*?)\]/) : null;
            if (keyMatch) manualEditedKeys.add(keyMatch[1]);

            const $row = $(this).closest('tr');
            const qty = parseFloat($(this).val()) || 0;
            const price = parseFloat($(this).data('price')) || 0;

            // 画面上の小計表示をリアルタイム更新（カンマ区切り）
            $row.find('.charge-subtotal-display').text((qty * price).toLocaleString() + "円");

            // 視認性の向上：数量が0の行は薄くして「見積に含まれない」ことを強調
            if (qty == 0) {
                $row.addClass('charge-row-zero text-muted opacity-50');
            } else {
                $row.removeClass('charge-row-zero text-muted opacity-50');
            }

            // サーバーには飛ばさず、今ある数値だけで合計金額を計算（高速応答）
            if (typeof finalTotalUpdateOnly === "function") finalTotalUpdateOnly();
            
            // ランフラット等の付随する工賃への影響を考慮し、裏でAPI計算を予約
            updateEstimateChargesDebounced();
        });

        /**
         * 【フォーム送信時の最終防衛ライン】
         * 保存ボタンが押された際、計算結果に矛盾がないか、不正な入力がないか最終確認
         */
        $('form#estimate-form').on('submit', function(e) {
            console.log("💾 見積データの整合性を確認し、保存を開始します...");
            // updateGrandTotalWithCharges が false（エラーあり）を返したら送信を中止
            // if (!updateGrandTotalWithCharges()) {
                // e.preventDefault();
                // alert("入力内容に不整合があるか、タイヤが選択されていません。内容を確認してください。");
            // }
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