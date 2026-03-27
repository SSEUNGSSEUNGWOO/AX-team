from agents import Agent, Team

# ─── 팀 구성 (원하는 대로 추가/수정 가능) ───────────────────────────
def build_default_team() -> Team:
    team = Team()
    team.add_agent(Agent(
        name="지민",
        role="마케팅 담당",
        description=(
            "시장 트렌드, 고객 세그먼트, 브랜딩, 마케팅 전략 전문가. "
            "항상 고객 관점과 시장 기회를 먼저 생각합니다."
        ),
    ))
    team.add_agent(Agent(
        name="준혁",
        role="개발 담당",
        description=(
            "소프트웨어 아키텍처, 기술 스택, 구현 가능성, 개발 일정 전문가. "
            "현실적인 기술 제약과 최선의 기술 솔루션을 제시합니다."
        ),
    ))
    team.add_agent(Agent(
        name="수아",
        role="비즈니스 모델 담당",
        description=(
            "수익 모델, 비용 구조, 파트너십, 사업 타당성 전문가. "
            "지속 가능한 비즈니스 모델과 성장 전략을 고민합니다."
        ),
    ))
    return team


def main():
    print("\n🤖 AX 팀 시뮬레이터")
    print("AI 전문가 팀이 당신의 아이디어를 함께 검토합니다.\n")

    team = build_default_team()

    print("팀 구성:")
    for agent in team.agents:
        print(f"  • {agent.name} ({agent.role})")

    print()

    while True:
        task = input("태스크를 입력하세요 (종료: q): ").strip()
        if task.lower() == "q":
            print("종료합니다.")
            break
        if not task:
            continue

        try:
            rounds = input("토론 라운드 수 (기본 2): ").strip()
            rounds = int(rounds) if rounds.isdigit() else 2
        except ValueError:
            rounds = 2

        team.run(task, discussion_rounds=rounds)


if __name__ == "__main__":
    main()
