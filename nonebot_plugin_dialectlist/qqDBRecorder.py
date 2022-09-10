import time

from datetime import datetime
from sqlmodel import select, or_
from typing_extensions import Literal
from typing import Iterable, List, Optional, Dict

from nonebot.log import logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Message
from nonebot.adapters.onebot.v11.exception import ActionFailed

from nonebot_plugin_datastore import create_session

from nonebot_plugin_chatrecorder.model import MessageRecord

from .config import plugin_config

async def get_message_records(
    user_ids: Optional[Iterable[str]] = None,
    group_ids: Optional[Iterable[str]] = None,
    platforms: Optional[Iterable[str]] = None,
    exclude_user_ids: Optional[Iterable[str]] = None,
    exclude_group_ids: Optional[Iterable[str]] = None,
    message_type: Optional[Literal['private', 'group']] = None,
    time_start: Optional[datetime] = None,
    time_stop: Optional[datetime] = None,
)->List[MessageRecord]:
    """
    :说明:

      获取消息记录

    :参数:
    
      * ``user_ids: Optional[Iterable[str]]``: 用户列表，为空表示所有用户
      * ``group_ids: Optional[Iterable[str]]``: 群组列表，为空表示所有群组
      * ``platform: OPtional[Iterable[str]]``: 消息来源列表，为空表示所有来源
      * ``exclude_user_ids: Optional[Iterable[str]]``: 不包含的用户列表，为空表示不限制
      * ``exclude_group_ids: Optional[Iterable[str]]``: 不包含的群组列表，为空表示不限制
      * ``message_type: Optional[Literal['private', 'group']]``: 消息类型，可选值：'private' 和 'group'，为空表示所有类型
      * ``time_start: Optional[datetime]``: 起始时间，UTC 时间，为空表示不限制起始时间
      * ``time_stop: Optional[datetime]``: 结束时间，UTC 时间，为空表示不限制结束时间

    :返回值:
      * ``List[MessageRecord]``:返回信息
    """

    whereclause = []
    if user_ids:
        whereclause.append(
            or_(*[MessageRecord.user_id == user_id for user_id in user_ids]) # type: ignore
        )
    if group_ids:
        whereclause.append(
            or_(*[MessageRecord.group_id == group_id for group_id in group_ids]) # type: ignore
        )
    if platforms:
        whereclause.append(
            or_(*[MessageRecord.platform == platform for platform in platforms])  # type: ignore
        )
    if exclude_user_ids:
        for user_id in exclude_user_ids:
            whereclause.append(MessageRecord.user_id != user_id)
    if exclude_group_ids:
        for group_id in exclude_group_ids:
            whereclause.append(MessageRecord.group_id != group_id)
    if message_type:
        whereclause.append(MessageRecord.detail_type == message_type)
    if time_start:
        whereclause.append(MessageRecord.time >= time_start)
    if time_stop:
        whereclause.append(MessageRecord.time <= time_stop)

    statement = select(MessageRecord).where(*whereclause)
    async with create_session() as session:
        records: List[MessageRecord] = (await session.exec(statement)).all() # type: ignore
    return records



async def msg_counter(
    gid:int,
    bot:Bot,
    msg:List[MessageRecord],
    got_num:int=10,
)->Message:
    '''
        计算出结果并返回可以直接发送的字符串
    '''
    st = time.time()
    
    logger.debug('loading msg from group {}'.format(gid))
    gnl = await bot.call_api('get_group_member_list',group_id=int(gid))
    logger.debug('group {} have number {}'.format(gid,len(gnl)))

    lst:Dict[str,int] = {}
    msg_len = len(msg)
    for i in msg:
        try:
            lst[i.user_id] +=1
        except KeyError:
            lst[i.user_id] =1

    logger.debug(lst)
    logger.debug('group number num is '+str(len(lst)))

    ranking = []
    while len(ranking) < got_num:
        
        try:
            maxkey = max(lst, key=lst.get)  # type: ignore
        except ValueError:
            ranking.append(("null",0))
            continue

        logger.debug('searching number {} from group {}'.format(str(maxkey),str(gid)))
        
        try:
            
            member_info = await bot.call_api(
                "get_group_member_info",
                group_id=int(gid),
                user_id=int(maxkey),
                no_cache=True
            )
            nickname:str = member_info['nickname']if not member_info['card'] else member_info['card']
            ranking.append([nickname.strip(),lst.pop(maxkey)])
            
        except ActionFailed as e:
            
            logger.warning(e)
            logger.warning('number {} is not exit in group {}'.format(str(maxkey),str(gid)))
            lst.pop(maxkey)

    logger.debug('loaded list:\n{}'.format(ranking))
    
    out:str = ''
    for i in range(got_num):
        index = i+1
        nickname,chatdatanum = str(ranking[i])
        str_example = plugin_config.dialectlist_string_format.format(index=index,nickname=nickname,chatdatanum=chatdatanum)
        out = out + str_example
        
    logger.debug(out)
    logger.info('spent {} seconds to count from {} msg'.format(time.time()-st,msg_len))
    
    return Message(out)