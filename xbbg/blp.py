import pandas as pd

from itertools import product
from xone import utils, files, logs

from xbbg import const, intervals, assist
from xbbg.conn import with_bloomberg, create_connection
from xbbg.timezone import DEFAULT_TZ
from xbbg.exchange import TradingHours, SessNA


@with_bloomberg
def bdp(tickers: (str, list), flds: (str, list), cache=False, **kwargs):
    """
    Get reference data and save to

    Args:
        tickers: tickers
        flds: fields to query
        cache: bool - use cache to store data
        **kwargs: overrides

    Returns:
        pd.DataFrame

    Examples:
        >>> bdp('IQ US Equity', 'Crncy')
                 ticker  field value
        0  IQ US Equity  Crncy   USD
    """
    logger = logs.get_logger(bdp)
    tickers = utils.flatten(tickers)
    flds = utils.flatten(flds)
    con, _ = create_connection()
    ovrds = assist._proc_ovrds_(**kwargs)

    if not cache:
        full_list = '\n'.join([f'tickers: {tickers[:8]}'] + [
            f'         {tickers[n:(n + 8)]}' for n in range(8, len(tickers), 8)
        ])
        logger.info(f'reference data for\n{full_list}\nfields: {flds}')
        return con.ref(tickers=tickers, flds=flds, ovrds=ovrds)

    cached_data = []
    cur_data, ref_data = pd.DataFrame(), pd.DataFrame()

    has_date = kwargs.pop('has_date', False)
    from_cache = kwargs.pop('from_cache', False)

    loaded = pd.DataFrame(data=0, index=tickers, columns=flds)
    for ticker, fld in product(tickers, flds):
        data_file = assist._ref_file_(
            ticker=ticker, fld=fld, has_date=has_date, from_cache=from_cache, **kwargs
        )
        if files.exists(data_file):
            cached_data.append(pd.read_parquet(data_file))
            loaded.loc[ticker, fld] = 1

    to_qry = loaded.where(loaded == 0).dropna(how='all', axis=1).dropna(how='all', axis=0)
    if not to_qry.empty:
        ref_tcks = to_qry.index.tolist()
        ref_flds = to_qry.columns.tolist()
        full_list = '\n'.join([f'tickers: {ref_tcks[:8]}'] + [
            f'         {ref_tcks[n:(n + 8)]}' for n in range(8, len(ref_tcks), 8)
        ])
        logger.info(f'loading reference data for\n{full_list}\nfields: {ref_flds}')
        ref_data = con.ref(tickers=ref_tcks, flds=ref_flds, ovrds=ovrds)

    for r, snap in ref_data.iterrows():
        subset = [r]
        data_file = assist._ref_file_(ticker=snap.ticker, fld=snap.field, **kwargs)
        if data_file:
            files.create_folder(data_file, is_file=True)
            ref_data.iloc[subset].to_parquet(data_file)
        cached_data.append(ref_data.iloc[subset])

    if len(cached_data) == 0: return pd.DataFrame()
    return pd.DataFrame(
        pd.concat(cached_data, sort=False)
    ).reset_index(drop=True).drop_duplicates(subset=['ticker', 'field'], keep='last')


@with_bloomberg
def bdh(
        tickers: (str, list), flds: (str, list),
        start_date: (str, pd.Timestamp), end_date: (str, pd.Timestamp), **kwargs
):
    """
    Bloomberg historical data

    Args:
        tickers: ticker(s)
        flds: field(s)
        start_date: start date
        end_date: end date
        **kwargs: overrides

    Returns:
        pd.DataFrame

    Examples:
        >>> flds = ['High', 'Low', 'Last_Price']
        >>> s_dt, e_dt = '2018-02-05', '2018-02-08'
        >>> d = bdh('VIX Index', flds, start_date=s_dt, end_date=e_dt).round(2)
        >>> d.index.name = None
        >>> r = d.transpose()
        >>> r.index.names = (None, None)
        >>> r
                              2018-02-05  2018-02-06  2018-02-07  2018-02-08
        VIX Index High             38.80       50.30       31.64       36.17
                  Low              16.80       22.42       21.17       24.41
                  Last_Price       37.32       29.98       27.73       33.46
    """
    logger = logs.get_logger(bdh)
    con, _ = create_connection()
    elms = assist._proc_elms_(**kwargs)
    ovrds = assist._proc_ovrds_(**kwargs)

    if isinstance(tickers, str): tickers = [tickers]
    if isinstance(flds, str): flds = [flds]
    s_dt = utils.fmt_dt(start_date, fmt='%Y-%m-%d')
    e_dt = utils.fmt_dt(end_date, fmt='%Y-%m-%d')

    full_list = '\n'.join([f'tickers: {tickers[:8]}'] + [
        f'         {tickers[n:(n + 8)]}' for n in range(8, len(tickers), 8)
    ])
    logger.info(f'loading historical data for\n{full_list}\nfields: {flds}')

    return con.bdh(
        tickers=tickers, flds=flds, elms=elms, ovrds=ovrds,
        start_date=s_dt.replace('-', ''), end_date=e_dt.replace('-', ''),
    )


@with_bloomberg
def bds(tickers: (str, list), flds: (str, list), cached=False, **kwargs):
    """
    Download block data from Bloomberg

    Args:
        tickers: ticker(s)
        flds: field(s)
        cached: whether read from cached
        **kwargs: other overrides for query

    Returns:
        pd.DataFrame: block data

    Examples:
        >>> pd.options.display.width = 120
        >>> s_dt, e_dt = '20180301', '20181031'
        >>> dvd = bds('NVDA US Equity', 'DVD_Hist_All', DVD_Start_Dt=s_dt, DVD_End_Dt=e_dt)
        >>> dvd.loc[:, ['ticker', 'name', 'value']]
                    ticker                name         value
        0   NVDA US Equity       Declared Date    2018-08-16
        1   NVDA US Equity             Ex-Date    2018-08-29
        2   NVDA US Equity         Record Date    2018-08-30
        3   NVDA US Equity        Payable Date    2018-09-21
        4   NVDA US Equity     Dividend Amount          0.15
        5   NVDA US Equity  Dividend Frequency       Quarter
        6   NVDA US Equity       Dividend Type  Regular Cash
        7   NVDA US Equity       Declared Date    2018-05-10
        8   NVDA US Equity             Ex-Date    2018-05-23
        9   NVDA US Equity         Record Date    2018-05-24
        10  NVDA US Equity        Payable Date    2018-06-15
        11  NVDA US Equity     Dividend Amount          0.15
        12  NVDA US Equity  Dividend Frequency       Quarter
        13  NVDA US Equity       Dividend Type  Regular Cash
    """
    logger = logs.get_logger(bds)
    tickers = utils.flatten(tickers, unique=True)
    flds = utils.flatten(flds, unique=True)
    con, _ = create_connection()
    ovrds = assist._proc_ovrds_(**kwargs)

    if not cached:
        return con.bulkref(tickers=tickers, flds=flds, ovrds=ovrds)

    cache_data = []
    loaded = pd.DataFrame(data=0, index=tickers, columns=flds)
    for ticker, fld in product(tickers, flds):
        data_file = assist._ref_file_(
            ticker=ticker, fld=fld, has_date=True, from_cache=cached, ext='pkl', **kwargs
        )
        logger.debug(f'checking file: {data_file}')
        if files.exists(data_file):
            logger.debug('[YES]')
            cache_data.append(pd.read_pickle(data_file))
            loaded.loc[ticker, fld] = 1

    logger.debug(f'\n{loaded.to_string()}')
    to_qry = loaded.where(loaded == 0).dropna(how='all', axis=1).dropna(how='all', axis=0)
    if not to_qry.empty:
        ref_tcks = to_qry.index.tolist()
        ref_flds = to_qry.columns.tolist()
        full_list = '\n'.join([f'tickers: {ref_tcks[:8]}'] + [
            f'         {ref_tcks[n:(n + 8)]}' for n in range(8, len(ref_tcks), 8)
        ])
        logger.info(f'loading block data for\ntickers: {full_list}\nfields: {ref_flds}')
        data = con.bulkref(tickers=ref_tcks, flds=ref_flds, ovrds=ovrds)
        for (ticker, fld), grp in data.groupby(['ticker', 'field']):
            data_file = assist._ref_file_(
                ticker=ticker, fld=fld, has_date=True, ext='pkl', **kwargs
            )
            if data_file:
                files.create_folder(data_file, is_file=True)
                grp.reset_index(drop=True).to_pickle(data_file)
            if to_qry.loc[ticker, fld] == 0: cache_data.append(grp)

    if len(cache_data) == 0: return pd.DataFrame()
    return pd.concat(cache_data, sort=False).reset_index(drop=True)


@with_bloomberg
def bdib(ticker: (str, list), dt: (str, pd.Timestamp), typ='TRADE', batch=False):
    """
    Download intraday data and save to cache

    Args:
        ticker: ticker name
        dt: date to download
        typ: [TRADE, BID, ASK, BID_BEST, ASK_BEST, BEST_BID, BEST_ASK]
        batch: whether is batch process to download data

    Returns:
        pd.DataFrame
    """
    logger = logs.get_logger(bdib)

    t_1 = pd.Timestamp('today').date() - pd.Timedelta('1D')
    whole_day = pd.Timestamp(dt).date() < t_1
    if (not whole_day) and batch:
        logger.warning(f'querying date {t_1} is too close, ignoring download ...')
        return None

    cur_dt = pd.Timestamp(dt).strftime('%Y-%m-%d')
    asset = ticker.split()[-1]
    data_file = assist._hist_file_(ticker=ticker, dt=dt, typ=typ)
    info_log = f'{ticker} / {cur_dt} / {typ}'

    if files.exists(data_file):
        if batch: return
        logger.info(f'reading from {data_file} ...')
        return pd.read_parquet(data_file)

    if asset in ['Equity', 'Curncy', 'Index', 'Comdty']:
        info = const.market_info(ticker=ticker)
        if any(k not in info for k in ['exch']):
            logger.warning(f'cannot find market info for {ticker}: {utils.to_str(info)}')
            return pd.DataFrame()
        exch = info['exch']
        assert isinstance(exch, TradingHours), ValueError(
            f'exch info for {ticker} is not TradingHours: {exch}'
        )

    else:
        logger.error(f'unknown asset type: {asset}')
        return pd.DataFrame()

    time_fmt = '%Y-%m-%dT%H:%M:%S'
    time_idx = pd.DatetimeIndex([
        f'{cur_dt} {exch.hours.allday.start_time}', f'{cur_dt} {exch.hours.allday.end_time}']
    ).tz_localize(exch.tz).tz_convert(DEFAULT_TZ).tz_convert('UTC')
    if time_idx[0] > time_idx[1]: time_idx -= pd.TimedeltaIndex(['1D', '0D'])

    q_tckr = ticker
    if info.get('is_fut', False):
        if 'freq' not in info:
            logger.error(f'[freq] missing in info for {info_log} ...')

        is_sprd = info.get('has_sprd', False) and (len(ticker[:-1]) != info['tickers'][0])
        if not is_sprd:
            q_tckr = fut_ticker(gen_ticker=ticker, dt=dt, freq=info['freq'])
            if q_tckr == '':
                logger.error(f'cannot find futures ticker for {ticker} ...')
                return pd.DataFrame()

    info_log = f'{q_tckr} / {cur_dt} / {typ}'
    cur_miss = assist.current_missing(ticker=ticker, dt=dt, typ=typ, func=bdib.__name__)
    if cur_miss >= 2:
        if batch: return
        logger.info(f'{cur_miss} trials with no data {info_log}')
        return pd.DataFrame()

    logger.info(f'loading data for {info_log} ...')
    con, _ = create_connection()
    data = con.bdib(
        ticker=q_tckr, event_type=typ, interval=1,
        start_datetime=time_idx[0].strftime(time_fmt),
        end_datetime=time_idx[1].strftime(time_fmt),
    )

    assert isinstance(data, pd.DataFrame)
    if data.empty:
        logger.warning(f'no data for {info_log} ...')
        assist.update_missing(ticker=ticker, dt=dt, typ=typ, func=bdib.__name__)
        return pd.DataFrame()

    data = data.tz_localize('UTC').tz_convert(exch.tz)
    assist._save_intraday_(data=data, ticker=ticker, dt=dt, typ=typ)

    return None if batch else data


def intraday(
        ticker: (str, list), dt: (str, pd.Timestamp), session='',
        start_time=None, end_time=None, typ='TRADE'
):
    """
    Retrieve interval data for ticker

    Args:
        ticker: ticker
        dt: date
        session: examples include
                 day_open_30, am_normal_30_30, day_close_30, allday_exact_0930_1000
        start_time: start time
        end_time: end time
        typ: [TRADE, BID, ASK, BID_BEST, ASK_BEST, BEST_BID, BEST_ASK]

    Returns:
        pd.DataFrame
    """
    cur_data = bdib(ticker=ticker, dt=dt, typ=typ)
    if cur_data.empty: return pd.DataFrame()

    fmt = '%H:%M:%S'
    ss = SessNA
    if session: ss = intervals.get_interval(ticker=ticker, session=session)

    if ss != SessNA:
        start_time = pd.Timestamp(ss.start_time).strftime(fmt)
        end_time = pd.Timestamp(ss.end_time).strftime(fmt)

    if start_time and end_time:
        return cur_data.between_time(start_time=start_time, end_time=end_time)

    return cur_data


@with_bloomberg
def active_futures(ticker: str, dt):
    """
    Active futures contract

    Args:
        ticker: futures ticker, i.e., ESA Index, Z A Index, CLA Comdty, etc.
        dt: date

    Returns:
        str: ticker name
    """
    t_info = ticker.split()
    prefix, asset = ' '.join(t_info[:-1]), t_info[-1]
    info = const.market_info(f'{prefix[:-1]}1 {asset}')

    f1, f2 = f'{prefix[:-1]}1 {asset}', f'{prefix[:-1]}2 {asset}'
    fut_2 = fut_ticker(gen_ticker=f2, dt=dt, freq=info['freq'])
    fut_1 = fut_ticker(gen_ticker=f1, dt=dt, freq=info['freq'])

    fut_tk = bdp(tickers=[fut_1, fut_2], flds='Last_Tradeable_Dt', cache=True)

    if pd.Timestamp(dt).month < pd.Timestamp(fut_tk.value[0]).month: return fut_1

    d1 = bdib(ticker=f1, dt=dt)
    d2 = bdib(ticker=f2, dt=dt)

    return fut_1 if d1.volume.sum() > d2.volume.sum() else fut_2


@with_bloomberg
def fut_ticker(gen_ticker: str, dt, freq: str):
    """
    Get proper ticker from generic ticker

    Args:
        gen_ticker: generic ticker
        dt: date
        freq: futures contract frequency

    Returns:
        str: exact futures ticker
    """
    logger = logs.get_logger(fut_ticker)
    dt = pd.Timestamp(dt)
    t_info = gen_ticker.split()

    asset = t_info[-1]
    if asset in ['Index', 'Curncy', 'Comdty']:
        ticker = ' '.join(t_info[:-1])
        prefix, idx, postfix = ticker[:-1], int(ticker[-1]) - 1, asset

    elif asset == 'Equity':
        ticker = t_info[0]
        prefix, idx, postfix = ticker[:-1], int(ticker[-1]) - 1, ' '.join(t_info[1:])

    else:
        logger.error(f'unkonwn asset type for ticker: {gen_ticker}')
        return ''

    month_ext = 4 if asset == 'Comdty' else 2
    months = pd.DatetimeIndex(start=dt, periods=max(idx + month_ext, 3), freq=freq)
    logger.debug(f'pulling expiry dates for months: {months}')

    def to_fut(month):
        return prefix + const.Futures[month.strftime('%b')] + \
               month.strftime('%y')[-1] + ' ' + postfix

    fut = [to_fut(m) for m in months]
    logger.debug(f'trying futures: {fut}')
    # noinspection PyBroadException
    try:
        fut_matu = bdp(tickers=fut, flds='last_tradeable_dt', cache=True)
    except Exception as e1:
        logger.error(f'error downloading futures contracts (1st trial) {e1}:\n{fut}')
        # noinspection PyBroadException
        try:
            fut = fut[:-1]
            logger.debug(f'trying futures (2nd trial): {fut}')
            fut_matu = bdp(tickers=fut, flds='last_tradeable_dt', cache=True)
        except Exception as e2:
            logger.error(f'error downloading futures contracts (2nd trial) {e2}:\n{fut}')
            return ''

    sub_fut = fut_matu[pd.DatetimeIndex(fut_matu.value) > dt]
    logger.debug(f'futures full chain:\n{fut_matu.to_string()}')
    logger.debug(f'getting index {idx} from:\n{sub_fut.to_string()}')
    return sub_fut.ticker.values[idx]


if __name__ == '__main__':
    """
    CommandLine:
        python -m xbbg.blp all
    """
    import xdoctest
    xdoctest.doctest_module(__file__)
