from video_chunking.data import ChunkMeta, MicroChunkMeta, MacroChunkMeta


def test_chunkmeta_timestamp_description_rounding():
    chunk = ChunkMeta()
    chunk.time_st = 1.4
    chunk.time_end = 9.6

    assert chunk.get_timestamp_desc() == "Start time: 1 sec\nEnd time: 10 sec"


def test_micro_and_macro_chunk_defaults():
    micro = MicroChunkMeta()
    macro = MacroChunkMeta()

    assert micro.level == 0
    assert micro.id == 0
    assert micro.desc == ""

    assert macro.level == 0
    assert macro.num_subchunk == 0
    assert macro.chunk_list == []
